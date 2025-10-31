from flask import Blueprint, request, jsonify, url_for, current_app
from flask_restful import Api, Resource
from models import *
from extensions import db
from utils.auth import buyer_required, farmer_required, delivery_agent_required, admin_required, any_authenticated_user
from utils.delivery import estimate_delivery_cost
from typing import Any, Dict, List, Optional
from utils.mpesa import (
    initiate_stk_push,
    extract_checkout_request_id,
    extract_mpesa_receipt,
    callback_successful,
)
from datetime import datetime, timezone
from utils.email_service import send_email

# Create blueprint for orders
orders_bp = Blueprint('orders', __name__)
api = Api(orders_bp)


def _format_address(location: Optional[Location]) -> Optional[str]:
    if not location:
        return None

    parts = [
        location.address_line,
        location.city,
        location.region,
        location.country,
    ]
    filtered = [part.strip() for part in parts if part]
    return ", ".join(filtered) if filtered else None


def _serialize_delivery_agent(user: Optional[User]) -> Optional[Dict[str, Any]]:
    if not user:
        return None

    profile = getattr(user, "delivery_agent_profile", None)
    location = profile.current_location if profile and profile.current_location else None
    return {
        "id": user.id,
        "name": user.name,
        "phone": profile.phone if profile else user.phone,
        "vehicle_type": profile.vehicle_type if profile else None,
        "vehicle_number": profile.vehicle_number if profile else None,
        "is_available": profile.is_available if profile else None,
        "location": {
            "latitude": float(location.latitude) if location and location.latitude is not None else None,
            "longitude": float(location.longitude) if location and location.longitude is not None else None,
        } if location else None,
    }


def _pickup_location_from_order(order: Order) -> Optional[Location]:
    for item in order.items:
        if item.product and item.product.location:
            return item.product.location
    return None


def _serialize_order_for_delivery(order: Order) -> Dict[str, Any]:
    pickup_location = _pickup_location_from_order(order)
    dropoff_location = order.shipping_address

    return {
        "id": order.id,
        "delivery_status": order.delivery_status.value,
        "payment_status": order.payment_status.value,
        "status": order.status.value,
        "placed_at": order.placed_at.isoformat() if order.placed_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        "total_price": float(order.total_price),
        "delivery_cost": float(order.delivery_cost),
        "buyer": {
            "id": order.buyer.id if order.buyer else None,
            "name": order.buyer.name if order.buyer else None,
        },
        "farmer": {
            "id": order.farmer.id if order.farmer else None,
            "name": order.farmer.name if order.farmer else None,
        },
        "delivery_group_id": order.delivery_group_id,
        "delivery_agent": _serialize_delivery_agent(order.delivery_agent),
        "pickup_address": _format_address(pickup_location),
        "dropoff_address": _format_address(dropoff_location),
        "pickup_location": pickup_location.to_dict() if pickup_location else None,
        "dropoff_location": dropoff_location.to_dict() if dropoff_location else None,
    }


def _serialize_tracking_payload(order: Order) -> Dict[str, Any]:
    pickup_location = _pickup_location_from_order(order)
    dropoff_location = order.shipping_address
    agent_info = _serialize_delivery_agent(order.delivery_agent)

    return {
        "order": {
            "id": order.id,
            "delivery_status": order.delivery_status.value,
            "payment_status": order.payment_status.value,
            "status": order.status.value,
            "placed_at": order.placed_at.isoformat() if order.placed_at else None,
            "updated_at": order.updated_at.isoformat() if order.updated_at else None,
            "total_price": float(order.total_price),
            "delivery_cost": float(order.delivery_cost),
        },
        "tracking": {
            "pickup": {
                "address": _format_address(pickup_location),
                "location": pickup_location.to_dict() if pickup_location else None,
            },
            "dropoff": {
                "address": _format_address(dropoff_location),
                "location": dropoff_location.to_dict() if dropoff_location else None,
            },
            "agent": agent_info,
            "status": order.delivery_status.value,
            "last_updated": order.updated_at.isoformat() if order.updated_at else None,
        }
    }


def _ensure_delivery_agent_profile(user: User) -> DeliveryAgent:
    profile = getattr(user, "delivery_agent_profile", None)
    if profile:
        return profile

    profile = DeliveryAgent(user_id=user.id, phone=user.phone)
    db.session.add(profile)
    db.session.flush()
    return profile


def _resolve_group_agent(group: DeliveryGroup) -> Optional[User]:
    for assignment in group.assignments:
        if assignment.agent:
            return assignment.agent
    for order in group.orders:
        if order.delivery_agent:
            return order.delivery_agent
    return None


def _calculate_agent_summary() -> List[Dict[str, Any]]:
    summary: Dict[int, Dict[str, Any]] = {}

    orders = Order.query.filter(Order.delivery_agent_id.isnot(None)).all()
    for order in orders:
        agent = order.delivery_agent
        if not agent:
            continue

        bucket = summary.setdefault(agent.id, {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "active": 0,
            "completed": 0,
            "pending": 0,
        })

        status_value = order.delivery_status.value
        if status_value in {OrderDeliveryStatus.ASSIGNED.value, OrderDeliveryStatus.OUT_FOR_DELIVERY.value}:
            bucket["active"] += 1
        elif status_value == OrderDeliveryStatus.DELIVERED.value:
            bucket["completed"] += 1
        else:
            bucket["pending"] += 1

    return list(summary.values())


def _send_notification(subject: str, recipients: List[str], body: str) -> None:
    payload = [{"email": email} for email in recipients if email]
    if not payload:
        return

    html_body = "<br>".join(body.splitlines())
    if not send_email(subject=subject, recipients=payload, text_body=body, html_body=html_body):
        current_app.logger.error("Failed to send notification '%s' via Brevo", subject)

def _format_order_lines(order: Order) -> str:
    if not order.items:
        return "- No items recorded"

    lines = []
    for item in order.items:
        product_name = item.product.name if item.product else f"Product #{item.product_id}"
        lines.append(f"- {product_name} x {item.quantity}")
    return "\n".join(lines)


def _notify_farmer_new_order(order: Order) -> None:
    farmer = order.farmer
    if not farmer or not farmer.email:
        return

    buyer_name = order.buyer.name if order.buyer else "an AgroLink buyer"
    delivery_address = _format_address(order.shipping_address) or "Delivery address provided at checkout"
    order_lines = _format_order_lines(order)
    total_amount = float(order.total_price or 0)

    body = f"""Hi {farmer.name},

You have a new order #{order.id} from {buyer_name} awaiting fulfilment.

Order summary:
{order_lines}

Total amount: KSh {total_amount:,.2f}
Deliver to: {delivery_address}

Log in to your AgroLink dashboard to review the order, confirm availability, and arrange delivery.

— AgroLink Team"""

    _send_notification(
        subject=f"New AgroLink order #{order.id}",
        recipients=[farmer.email],
        body=body,
    )


def _agent_contact_phone(agent: User) -> Optional[str]:
    profile = getattr(agent, "delivery_agent_profile", None)
    if profile and profile.phone:
        return profile.phone
    return agent.phone


def _notify_assignment_emails(order: Order, agent: User) -> None:
    pickup_address = _format_address(_pickup_location_from_order(order)) or "Farmer location on record"
    dropoff_address = _format_address(order.shipping_address) or "Buyer delivery address"
    order_lines = _format_order_lines(order)
    farmer = order.farmer
    buyer = order.buyer
    agent_phone = _agent_contact_phone(agent)

    if agent.email:
        buyer_name = buyer.name if buyer else "AgroLink buyer"
        farmer_name = farmer.name if farmer else "your assigned farmer"
        body = f"""Hello {agent.name},

You have been assigned order #{order.id} from {farmer_name}.

Order summary:
{order_lines}

Pick up from: {pickup_address}
Deliver to: {dropoff_address}
Buyer contact: {buyer_name}{f' | {buyer.phone}' if buyer and buyer.phone else ''}

Please confirm pick-up with the farmer and update the delivery status in the AgroLink dashboard.

— AgroLink Team"""

        _send_notification(
            subject=f"AgroLink delivery assignment #{order.id}",
            recipients=[agent.email],
            body=body,
        )

    if buyer and buyer.email:
        agent_contact_line = f"{agent.name}{f' | {agent_phone}' if agent_phone else ''}"
        body = f"""Hi {buyer.name},

Your AgroLink order #{order.id} has been allocated to a delivery agent.

Delivery agent: {agent_contact_line}
Delivering from: {pickup_address}
Delivering to: {dropoff_address}

They will contact you ahead of delivery. You can track progress from your orders page on AgroLink.

— AgroLink Team"""

        _send_notification(
            subject=f"Order #{order.id} is on its way",
            recipients=[buyer.email],
            body=body,
        )


STATUS_TO_ASSIGNMENT_STATUS = {
    OrderDeliveryStatus.ASSIGNED.value: DeliveryAssignmentStatus.ASSIGNED,
    OrderDeliveryStatus.OUT_FOR_DELIVERY.value: DeliveryAssignmentStatus.IN_TRANSIT,
    OrderDeliveryStatus.DELIVERED.value: DeliveryAssignmentStatus.DELIVERED,
    OrderDeliveryStatus.CANCELLED.value: DeliveryAssignmentStatus.FAILED,
    OrderDeliveryStatus.RETURNED.value: DeliveryAssignmentStatus.FAILED,
}


class OrderList(Resource):
    @any_authenticated_user
    def post(self, current_user):
        """Create a new order from cart items"""
        data = request.get_json()
        
        # Get buyer's cart
        cart = Cart.query.filter_by(buyer_id=current_user.id).first()
        if not cart or not cart.items:
            return {"error": "Cart is empty"}, 400
        
        # Get shipping address
        shipping_address_id = data.get("shipping_address_id")
        if not shipping_address_id:
            return {"error": "Shipping address is required"}, 400
        
        shipping_address = Location.query.get(shipping_address_id)
        if not shipping_address:
            return {"error": "Invalid shipping address"}, 400
        
        try:
            # Calculate totals
            total_items_amount = 0
            order_items = []
            
            for cart_item in cart.items:
                if not cart_item.product.is_available or cart_item.product.quantity < cart_item.quantity:
                    return {"error": f"Product {cart_item.product.name} is not available in requested quantity"}, 400
                
                item_total = float(cart_item.product.price) * cart_item.quantity
                total_items_amount += item_total
                
                order_items.append({
                    "product_id": cart_item.product_id,
                    "quantity": cart_item.quantity,
                    "price_at_purchase": cart_item.product.price,
                    "weight_per_unit": cart_item.product.weight_per_unit
                })
            
            # Calculate delivery cost using a pluggable stub so the flow is ready for
            # a real provider once credentials are available.
            delivery_quote = estimate_delivery_cost(cart.items, shipping_address)
            delivery_cost = float(delivery_quote.get("amount", 0))
            total_price = total_items_amount + delivery_cost
            
            # Get the first farmer (simplified - in reality would handle multiple farmers)
            farmer_id = cart.items[0].product.farmer_id
            
            # Create order
            order = Order(
                buyer_id=current_user.id,
                farmer_id=farmer_id,
                shipping_address_id=shipping_address_id,
                total_items_amount=total_items_amount,
                delivery_cost=delivery_cost,
                total_price=total_price,
                payment_status=PaymentStatus.PENDING,
                delivery_status=OrderDeliveryStatus.PROCESSING,
                status=OrderStatus.PLACED
            )
            
            db.session.add(order)
            db.session.flush()  # Get order ID
            
            # Create order items
            for item_data in order_items:
                order_item = OrderItem(
                    order_id=order.id,
                    product_id=item_data["product_id"],
                    quantity=item_data["quantity"],
                    price_at_purchase=item_data["price_at_purchase"],
                    weight_per_unit=item_data["weight_per_unit"]
                )
                db.session.add(order_item)
                
                # Update product quantity
                product = Product.query.get(item_data["product_id"])
                product.quantity -= item_data["quantity"]
            
            # Clear cart
            CartItem.query.filter_by(cart_id=cart.id).delete()
            cart.updated_at = datetime.now(timezone.utc)
            
            db.session.commit()

            try:
                _notify_farmer_new_order(order)
            except Exception as exc:  # pragma: no cover - avoid interrupting checkout
                current_app.logger.error("Failed to send farmer notification for order %s: %s", order.id, exc)
            
            return {
                "message": "Order created successfully",
                "order": order.to_dict(),
                "delivery_quote": delivery_quote,
            }, 201
            
        except Exception as e:
            db.session.rollback()
            return {"error": f"Failed to create order: {str(e)}"}, 500

    @any_authenticated_user
    def get(self, current_user):
        """Get orders for current user"""
        role = current_user.get_role_name()
        
        if role == "buyer":
            orders = Order.query.filter_by(buyer_id=current_user.id).order_by(Order.placed_at.desc()).all()
        elif role == "farmer":
            orders = Order.query.filter_by(farmer_id=current_user.id).order_by(Order.placed_at.desc()).all()
        elif role == "delivery_agent":
            orders = Order.query.filter_by(delivery_agent_id=current_user.id).order_by(Order.placed_at.desc()).all()
        elif role == "superadmin":
            orders = Order.query.order_by(Order.placed_at.desc()).all()
        else:
            return {"error": "Invalid role"}, 403
        
        return {
            "orders": [order.to_dict() for order in orders]
        }, 200


class OrderDetail(Resource):
    @any_authenticated_user
    def get(self, order_id, current_user):
        """Get order details"""
        order = Order.query.get_or_404(order_id)
        
        # Check permissions
        role = current_user.get_role_name()
        if role not in ["superadmin"] and order.buyer_id != current_user.id and order.farmer_id != current_user.id and order.delivery_agent_id != current_user.id:
            return {"error": "Access denied"}, 403
        
        return {"order": order.to_dict()}, 200

    @any_authenticated_user
    def patch(self, order_id, current_user):
        """Update order status"""
        order = Order.query.get_or_404(order_id)
        data = request.get_json()
        
        role = current_user.get_role_name()
        
        # Only certain roles can update certain statuses
        if role == "delivery_agent" and order.delivery_agent_id == current_user.id:
            # Delivery agent can update delivery status
            delivery_status = data.get("delivery_status")
            if delivery_status and delivery_status in [status.value for status in OrderDeliveryStatus]:
                order.delivery_status = OrderDeliveryStatus(delivery_status)
                order.updated_at = datetime.now(timezone.utc)
                db.session.commit()
                return {"message": "Order status updated", "order": order.to_dict()}, 200
        
        elif role == "superadmin":
            # Admin can update any status
            for field in ["payment_status", "delivery_status", "status", "delivery_agent_id"]:
                if field in data:
                    if field == "payment_status":
                        order.payment_status = PaymentStatus(data[field])
                    elif field == "delivery_status":
                        order.delivery_status = OrderDeliveryStatus(data[field])
                    elif field == "status":
                        order.status = OrderStatus(data[field])
                    else:
                        setattr(order, field, data[field])
            
            order.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            return {"message": "Order updated", "order": order.to_dict()}, 200
        
        return {"error": "Permission denied"}, 403


class PaymentInit(Resource):
    @buyer_required
    def post(self, order_id, current_user):
        """Initialize payment for an order"""
        order = Order.query.get_or_404(order_id)
        
        # Check if user owns this order
        if order.buyer_id != current_user.id:
            return {"error": "Access denied"}, 403
        
        # Check if order is already paid
        if order.payment_status != PaymentStatus.PENDING:
            return {"error": f"Order is already {order.payment_status.value}"}, 400
        
        try:
            payment = Payment(
                order_id=order.id,
                amount=order.total_price,
                method="mpesa_stk",
                status=PaymentStatus.INITIATED,
                initiated_at=datetime.now(timezone.utc)
            )

            db.session.add(payment)

            order.payment_status = PaymentStatus.INITIATED
            order.updated_at = datetime.now(timezone.utc)

            db.session.flush()

            callback_url = None
            try:
                callback_url = url_for('orders.mpesacallbackresource', _external=True)
            except RuntimeError:
                # Running outside a request context (e.g. during CLI tests).
                callback_url = None

            mpesa_request = initiate_stk_push(order=order, payment=payment, callback_url=callback_url)

            checkout_request_id = mpesa_request.get("checkout_request_id")
            if checkout_request_id:
                payment.transaction_id = checkout_request_id

            db.session.commit()

            return {
                "message": "Payment initiated successfully",
                "payment": payment.to_dict(),
                "order": order.to_dict(),
                "mpesa_request": mpesa_request,
            }, 200

        except Exception as e:
            db.session.rollback()
            return {"error": f"Payment initiation failed: {str(e)}"}, 500


class MpesaCallbackResource(Resource):
    def post(self):
        payload = request.get_json(silent=True) or {}
        if not payload:
            return {"error": "Invalid callback payload"}, 400

        checkout_request_id = extract_checkout_request_id(payload)

        payment = None
        if checkout_request_id:
            payment = Payment.query.filter_by(transaction_id=checkout_request_id).order_by(Payment.created_at.desc()).first()

        payment_id = payment.id if payment else None

        callback_record = MpesaCallback(payment_id=payment_id, payload=payload)
        db.session.add(callback_record)

        try:
            if payment:
                if callback_successful(payload):
                    payment.status = PaymentStatus.PAID
                    payment.completed_at = datetime.now(timezone.utc)
                    receipt_number = extract_mpesa_receipt(payload)
                    if receipt_number:
                        payment.transaction_id = receipt_number

                    if payment.order:
                        payment.order.payment_status = PaymentStatus.PAID
                        payment.order.updated_at = datetime.now(timezone.utc)
                else:
                    payment.status = PaymentStatus.FAILED
                    if payment.order:
                        payment.order.payment_status = PaymentStatus.FAILED
                        payment.order.updated_at = datetime.now(timezone.utc)

            db.session.commit()

            return {
                "message": "Callback received",
                "checkout_request_id": checkout_request_id,
                "payment_id": payment_id,
            }, 200

        except Exception as e:
            db.session.rollback()
            return {"error": f"Failed to record callback: {str(e)}"}, 500


class DeliveryGroupList(Resource):
    @admin_required
    def get(self, current_user):
        """Get all delivery groups"""
        groups = DeliveryGroup.query.order_by(DeliveryGroup.created_at.desc()).all()

        payload = []
        for group in groups:
            agent_user = _resolve_group_agent(group)
            payload.append({
                "id": group.id,
                "group_name": group.group_name,
                "region": group.region,
                "status": group.status,
                "distance_estimate": float(group.distance_estimate) if group.distance_estimate is not None else None,
                "created_at": group.created_at.isoformat() if group.created_at else None,
                "order_count": len(group.orders),
                "delivery_agent": _serialize_delivery_agent(agent_user),
                "orders": [_serialize_order_for_delivery(order) for order in group.orders],
            })

        return {
            "delivery_groups": payload,
            "agent_summary": _calculate_agent_summary(),
        }, 200
    
    @admin_required
    def post(self, current_user):
        """Create a delivery group and assign orders"""
        data = request.get_json()
        
        try:
            # Get paid orders in processing status for the same region
            region = data.get("region")
            if not region:
                return {"error": "Region is required"}, 400
            
            # Create delivery group
            distance_estimate = data.get("distance_estimate")
            if distance_estimate is not None:
                try:
                    distance_estimate = float(distance_estimate)
                except (TypeError, ValueError):
                    return {"error": "distance_estimate must be numeric"}, 400
            else:
                distance_estimate = 0

            default_name = data.get("group_name") or f"Group {region} {datetime.now().strftime('%Y%m%d')}"

            delivery_group = DeliveryGroup(
                group_name=default_name,
                region=region,
                status="created",
                distance_estimate=distance_estimate
            )
            
            db.session.add(delivery_group)
            db.session.flush()
            
            # Assign orders to the group
            order_ids = data.get("order_ids", [])
            if order_ids:
                orders = Order.query.filter(
                    Order.id.in_(order_ids),
                    Order.payment_status == PaymentStatus.PAID,
                    Order.delivery_status == OrderDeliveryStatus.PROCESSING
                ).all()
                
                for order in orders:
                    order.delivery_group_id = delivery_group.id
                    order.delivery_status = OrderDeliveryStatus.ASSIGNED
                    order.updated_at = datetime.now(timezone.utc)
            
            db.session.commit()
            
            return {
                "message": "Delivery group created successfully",
                "delivery_group": delivery_group.to_dict()
            }, 201
            
        except Exception as e:
            db.session.rollback()
            return {"error": f"Failed to create delivery group: {str(e)}"}, 500


class FarmerDeliveryAgentsResource(Resource):
    @farmer_required
    def get(self, current_user):
        include_unavailable = str(request.args.get("include_unavailable", "false")).lower() in {"true", "1", "yes"}

        agents_query = User.query.join(Role, User.role_id == Role.id).filter(Role.name == RoleName.DELIVERY_AGENT)

        if not include_unavailable:
            agents_query = agents_query.outerjoin(DeliveryAgent, DeliveryAgent.user_id == User.id).filter(
                (DeliveryAgent.is_available.is_(True)) | (DeliveryAgent.id.is_(None))
            )

        agents = agents_query.order_by(User.name.asc()).all()
        payload: List[Dict[str, Any]] = []
        for agent in agents:
            serialised = _serialize_delivery_agent(agent)
            if serialised:
                payload.append(serialised)

        return {"agents": payload}, 200


class FarmerAssignDeliveryAgent(Resource):
    @farmer_required
    def post(self, order_id, current_user):
        order = Order.query.get_or_404(order_id)
        if order.farmer_id != current_user.id:
            return {"error": "You can only manage delivery for your own orders"}, 403

        data = request.get_json() or {}
        agent_id = data.get("agent_id")
        if not agent_id:
            return {"error": "agent_id is required"}, 400

        agent = User.query.get(agent_id)
        if not agent or agent.get_role_name() != "delivery_agent":
            return {"error": "Invalid delivery agent"}, 400

        profile = _ensure_delivery_agent_profile(agent)
        now = datetime.now(timezone.utc)

        assignment = DeliveryAssignment.query.filter_by(order_id=order.id).order_by(DeliveryAssignment.assigned_at.desc()).first()
        if assignment:
            assignment.agent_id = agent.id
            assignment.status = DeliveryAssignmentStatus.ASSIGNED
            assignment.updated_at = now
        else:
            assignment = DeliveryAssignment(
                order_id=order.id,
                agent_id=agent.id,
                status=DeliveryAssignmentStatus.ASSIGNED,
                assigned_at=now,
                updated_at=now,
            )
            db.session.add(assignment)

        order.delivery_agent_id = agent.id
        if order.delivery_status in {OrderDeliveryStatus.PROCESSING, OrderDeliveryStatus.ASSIGNED}:
            order.delivery_status = OrderDeliveryStatus.ASSIGNED
        order.updated_at = now

        profile.is_available = False

        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            return {"error": f"Failed to assign delivery agent: {exc}"}, 500

        try:
            _notify_assignment_emails(order, agent)
        except Exception as exc:  # pragma: no cover - don’t block workflow on email failure
            current_app.logger.error(
                "Failed to send assignment notifications for order %s: %s", order.id, exc
            )

        return {
            "message": "Delivery agent assigned successfully",
            "order": _serialize_order_for_delivery(order),
        }, 200


class AssignDeliveryAgent(Resource):
    @admin_required
    def post(self, current_user):
        """Assign delivery agent to orders or delivery group"""
        data = request.get_json()
        
        agent_id = data.get("agent_id")
        order_ids = data.get("order_ids", [])
        delivery_group_id = data.get("delivery_group_id")
        
        if not agent_id:
            return {"error": "Agent ID is required"}, 400
        
        # Verify agent exists and has delivery_agent role
        agent = User.query.get(agent_id)
        if not agent or agent.get_role_name() != "delivery_agent":
            return {"error": "Invalid delivery agent"}, 400

        profile = _ensure_delivery_agent_profile(agent)
        
        try:
            updated_orders = []
            now = datetime.now(timezone.utc)
            delivery_group: Optional[DeliveryGroup] = None
            
            if delivery_group_id:
                delivery_group = DeliveryGroup.query.get_or_404(delivery_group_id)
                orders = list(delivery_group.orders)
            else:
                if not order_ids:
                    return {"error": "Provide either delivery_group_id or order_ids"}, 400
                orders = Order.query.filter(Order.id.in_(order_ids)).all()
            
            if not orders:
                return {"error": "No matching orders found"}, 404
            
            for order in orders:
                order.delivery_agent_id = agent_id
                if order.delivery_status in {OrderDeliveryStatus.PROCESSING, OrderDeliveryStatus.ASSIGNED}:
                    order.delivery_status = OrderDeliveryStatus.ASSIGNED
                order.updated_at = now
                if delivery_group and not order.delivery_group_id:
                    order.delivery_group_id = delivery_group.id

                assignment = DeliveryAssignment.query.filter_by(order_id=order.id).order_by(DeliveryAssignment.assigned_at.desc()).first()
                if assignment:
                    assignment.agent_id = agent_id
                    assignment.delivery_group_id = delivery_group.id if delivery_group else assignment.delivery_group_id
                    assignment.status = DeliveryAssignmentStatus.ASSIGNED
                    assignment.updated_at = now
                else:
                    assignment = DeliveryAssignment(
                        order_id=order.id,
                        agent_id=agent_id,
                        delivery_group_id=delivery_group.id if delivery_group else delivery_group_id,
                        status=DeliveryAssignmentStatus.ASSIGNED,
                        assigned_at=now,
                        updated_at=now,
                    )
                    db.session.add(assignment)

                updated_orders.append(_serialize_order_for_delivery(order))

            if delivery_group:
                delivery_group.status = "assigned"

            profile.is_available = False
            
            db.session.commit()
            
            return {
                "message": f"Assigned {len(updated_orders)} orders to delivery agent",
                "orders": updated_orders
            }, 200
            
        except Exception as e:
            db.session.rollback()
            return {"error": f"Assignment failed: {str(e)}"}, 500


class DeliveryReadyOrders(Resource):
    @admin_required
    def get(self, current_user):
        """List orders that are ready for delivery grouping."""

        region = request.args.get("region")
        status_filters = (
            OrderDeliveryStatus.PROCESSING,
            OrderDeliveryStatus.ASSIGNED,
        )

        query = Order.query.filter(
            Order.payment_status == PaymentStatus.PAID,
            Order.delivery_status.in_(status_filters),
        )

        if region:
            query = query.join(Location, Order.shipping_address_id == Location.id).filter(Location.region == region)

        orders = query.order_by(Order.placed_at.asc()).all()

        return {
            "orders": [_serialize_order_for_delivery(order) for order in orders],
        }, 200


class DeliveryGroupDetail(Resource):
    @admin_required
    def get(self, group_id, current_user):
        group = DeliveryGroup.query.get_or_404(group_id)
        agent_user = _resolve_group_agent(group)

        return {
            "delivery_group": {
                "id": group.id,
                "group_name": group.group_name,
                "region": group.region,
                "status": group.status,
                "distance_estimate": float(group.distance_estimate) if group.distance_estimate is not None else None,
                "created_at": group.created_at.isoformat() if group.created_at else None,
                "order_count": len(group.orders),
                "delivery_agent": _serialize_delivery_agent(agent_user),
                "orders": [_serialize_order_for_delivery(order) for order in group.orders],
            }
        }, 200

    @admin_required
    def patch(self, group_id, current_user):
        group = DeliveryGroup.query.get_or_404(group_id)
        data = request.get_json() or {}

        try:
            if "group_name" in data:
                group.group_name = data["group_name"]
            if "status" in data:
                group.status = data["status"]
            if "distance_estimate" in data:
                try:
                    value = data["distance_estimate"]
                    group.distance_estimate = float(value) if value is not None else None
                except (TypeError, ValueError):
                    return {"error": "distance_estimate must be numeric"}, 400

            order_ids = data.get("order_ids", [])
            if order_ids:
                orders = Order.query.filter(Order.id.in_(order_ids)).all()
                for order in orders:
                    order.delivery_group_id = group.id
                    if order.delivery_status == OrderDeliveryStatus.PROCESSING:
                        order.delivery_status = OrderDeliveryStatus.ASSIGNED
                    order.updated_at = datetime.now(timezone.utc)

            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            return {"error": f"Failed to update delivery group: {exc}"}, 500

        return self.get(group_id, current_user)


class DeliveryAgentOrdersResource(Resource):
    @delivery_agent_required
    def get(self, current_user):
        orders = Order.query.filter_by(delivery_agent_id=current_user.id).order_by(Order.placed_at.desc()).all()
        return {
            "orders": [_serialize_order_for_delivery(order) for order in orders]
        }, 200


class DeliveryAgentStatusResource(Resource):
    @delivery_agent_required
    def get(self, current_user):
        profile = _ensure_delivery_agent_profile(current_user)
        db.session.commit()  # Ensure profile persists if newly created
        return {"agent": _serialize_delivery_agent(current_user)}, 200

    @delivery_agent_required
    def patch(self, current_user):
        data = request.get_json() or {}
        profile = _ensure_delivery_agent_profile(current_user)

        try:
            if "is_available" in data:
                profile.is_available = bool(data.get("is_available"))

            latitude = data.get("latitude")
            longitude = data.get("longitude")

            if latitude is not None and longitude is not None:
                try:
                    lat = float(latitude)
                    lng = float(longitude)
                except (TypeError, ValueError):
                    return {"error": "Latitude and longitude must be numeric"}, 400

                location = profile.current_location
                if not location:
                    location = Location(
                        user_id=current_user.id,
                        label=data.get("label") or "Agent Current Position",
                        address_line=data.get("address_line"),
                        city=data.get("city"),
                        region=data.get("region"),
                        country=data.get("country"),
                        latitude=lat,
                        longitude=lng,
                    )
                    db.session.add(location)
                    db.session.flush()
                    profile.current_location_id = location.id
                else:
                    location.latitude = lat
                    location.longitude = lng
                    if data.get("address_line"):
                        location.address_line = data["address_line"]
                    if data.get("city"):
                        location.city = data["city"]
                    if data.get("region"):
                        location.region = data["region"]
                    if data.get("country"):
                        location.country = data["country"]

            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            return {"error": f"Failed to update agent status: {exc}"}, 500

        return {"agent": _serialize_delivery_agent(current_user)}, 200


class OrderStatusUpdateResource(Resource):
    @any_authenticated_user
    def patch(self, order_id, current_user):
        order = Order.query.get_or_404(order_id)
        data = request.get_json() or {}

        requested_status = data.get("delivery_status")
        if not requested_status:
            return {"error": "delivery_status is required"}, 400

        valid_statuses = {status.value for status in OrderDeliveryStatus}
        if requested_status not in valid_statuses:
            return {"error": "Invalid delivery status"}, 400

        role = current_user.get_role_name()
        if role == "delivery_agent" and order.delivery_agent_id != current_user.id:
            return {"error": "Access denied"}, 403
        if role not in {"delivery_agent", "superadmin"}:
            return {"error": "Permission denied"}, 403

        order.delivery_status = OrderDeliveryStatus(requested_status)
        order.updated_at = datetime.now(timezone.utc)

        assignment = DeliveryAssignment.query.filter_by(order_id=order.id).order_by(DeliveryAssignment.assigned_at.desc()).first()
        mapped_status = STATUS_TO_ASSIGNMENT_STATUS.get(requested_status)
        if assignment and mapped_status:
            assignment.status = mapped_status
            assignment.updated_at = datetime.now(timezone.utc)

        if order.delivery_status == OrderDeliveryStatus.DELIVERED and order.delivery_agent:
            remaining = Order.query.filter(
                Order.delivery_agent_id == order.delivery_agent_id,
                Order.delivery_status != OrderDeliveryStatus.DELIVERED
            ).count()
            if remaining == 0:
                profile = _ensure_delivery_agent_profile(order.delivery_agent)
                profile.is_available = True

        db.session.commit()

        return {"order": _serialize_order_for_delivery(order)}, 200


class OrderTrackingResource(Resource):
    @any_authenticated_user
    def get(self, order_id, current_user):
        order = Order.query.get_or_404(order_id)

        role = current_user.get_role_name()
        allowed = {
            order.buyer_id,
            order.delivery_agent_id,
            order.farmer_id,
        }

        if role != "superadmin" and current_user.id not in allowed:
            return {"error": "Access denied"}, 403

        return _serialize_tracking_payload(order), 200


# Register resources
api.add_resource(OrderList, '/orders')
api.add_resource(OrderDetail, '/orders/<int:order_id>')
api.add_resource(PaymentInit, '/orders/<int:order_id>/payment')
api.add_resource(DeliveryGroupList, '/delivery-groups')
api.add_resource(DeliveryGroupDetail, '/delivery-groups/<int:group_id>')
api.add_resource(DeliveryReadyOrders, '/delivery/orders/ready')
api.add_resource(DeliveryAgentOrdersResource, '/delivery-agents/me/orders')
api.add_resource(DeliveryAgentStatusResource, '/delivery-agents/me/status')
api.add_resource(OrderStatusUpdateResource, '/orders/<int:order_id>/status')
api.add_resource(OrderTrackingResource, '/orders/<int:order_id>/tracking')
api.add_resource(FarmerDeliveryAgentsResource, '/orders/delivery-agents')
api.add_resource(FarmerAssignDeliveryAgent, '/orders/<int:order_id>/assign-agent')
api.add_resource(AssignDeliveryAgent, '/assign-delivery-agent')
api.add_resource(MpesaCallbackResource, '/payments/mpesa/callback')