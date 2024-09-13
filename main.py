from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import logging
import db_helper
import generic_helper

app = FastAPI()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-progress orders storage
inprogress_orders = {}

# Intent handler functions
def add_to_order(parameters: dict, session_id: str):
    food_items = parameters.get("food-items", [])  # Updated from "food-item"
    quantities = parameters.get("number", [])

    if len(food_items) != len(quantities):
        fulfillment_text = "Sorry I didn't understand. Can you please specify food items and quantities clearly?"
    else:
        new_food_dict = dict(zip(food_items, quantities))

        if session_id in inprogress_orders:
            current_food_dict = inprogress_orders[session_id]
            current_food_dict.update(new_food_dict)
            inprogress_orders[session_id] = current_food_dict
        else:
            inprogress_orders[session_id] = new_food_dict

        order_str = generic_helper.get_str_from_food_dict(inprogress_orders[session_id])
        fulfillment_text = f"So far you have: {order_str}. Do you need anything else?"

    return JSONResponse(content={"fulfillmentText": fulfillment_text})

def remove_from_order(parameters: dict, session_id: str):
    if session_id not in inprogress_orders:
        return JSONResponse(content={
            "fulfillmentText": "I'm having trouble finding your order. Sorry! Can you place a new order please?"})

    food_items = parameters.get("food-items", [])  # Updated from "food-item"
    current_order = inprogress_orders[session_id]

    removed_items = []
    no_such_items = []

    for item in food_items:
        if item not in current_order:
            no_such_items.append(item)
        else:
            removed_items.append(item)
            del current_order[item]

    fulfillment_text = ""
    if len(removed_items) > 0:
        fulfillment_text += f'Removed {",".join(removed_items)} from your order!'
    if len(no_such_items) > 0:
        fulfillment_text += f' Your current order does not have {",".join(no_such_items)}'
    if len(current_order.keys()) == 0:
        fulfillment_text += " Your order is empty!"
    else:
        order_str = generic_helper.get_str_from_food_dict(current_order)
        fulfillment_text += f" Here is what is left in your order: {order_str}"

    return JSONResponse(content={"fulfillmentText": fulfillment_text})

def complete_order(parameters: dict, session_id: str):
    if session_id not in inprogress_orders:
        fulfillment_text = "I'm having trouble finding your order. Sorry! Can you place a new order please?"
    else:
        order = inprogress_orders[session_id]
        order_id = save_to_db(order)
        if order_id == -1:
            fulfillment_text = "Sorry, I couldn't process your order due to a backend error. Please place a new order again."
        else:
            order_total = db_helper.get_total_order_price(order_id)
            fulfillment_text = f"Awesome. We have placed your order. Here is your order id # {order_id}. Your order total is {order_total} which you can pay at the time of delivery!"
        del inprogress_orders[session_id]

    return JSONResponse(content={"fulfillmentText": fulfillment_text})

def track_order(parameters: dict, session_id: str = ''):
    order_id_str = parameters.get('number')

    if order_id_str is None:
        return JSONResponse(content={"fulfillmentText": "Order ID is missing or invalid."}, status_code=400)

    try:
        if isinstance(order_id_str, float):
            order_id = int(order_id_str)
        elif isinstance(order_id_str, str):
            order_id = int(order_id_str)
        elif isinstance(order_id_str, int):
            order_id = order_id_str
        else:
            return JSONResponse(content={"fulfillmentText": "Order ID is not a valid format."}, status_code=400)
    except ValueError:
        return JSONResponse(content={"fulfillmentText": "Order ID is not a valid integer."}, status_code=400)

    try:
        order_status = db_helper.get_order_status(order_id)
        if order_status:
            fulfillment_text = f"The order status for order id: {order_id} is: {order_status}"
        else:
            fulfillment_text = f"No order found with order id: {order_id}"
    except Exception as e:
        logger.error(f"Error fetching order status: {e}")
        return JSONResponse(content={"fulfillmentText": "Error fetching order status."}, status_code=500)

    return JSONResponse(content={"fulfillmentText": fulfillment_text})

def save_to_db(order: dict):
    next_order_id = db_helper.get_next_order_id()

    for food_item, quantity in order.items():
        rcode = db_helper.insert_order_item(
            food_item,
            quantity,
            next_order_id
        )

        if rcode == -1:
            return -1

    db_helper.insert_order_tracking(next_order_id, "in progress")

    return next_order_id

# Intent handler dictionary
intent_handler_dict = {
    'order.add - context: ongoing-order': add_to_order,
    'order.remove - context: ongoing-order': remove_from_order,
    'order.complete - context: ongoing-order': complete_order,
    'track.order - context: ongoing-tracking': track_order
}

@app.post("/")
async def handle_request(request: Request):
    try:
        payload = await request.json()
        logger.info(f"Received payload: {payload}")

        intent = payload.get('queryResult', {}).get('intent', {}).get('displayName')
        parameters = payload.get('queryResult', {}).get('parameters', {})
        session_id = payload.get('session', '')

        logger.info(f"Intent: {intent}")
        logger.info(f"Parameters: {parameters}")
        logger.info(f"Session ID: {session_id}")

        if intent in intent_handler_dict:
            return intent_handler_dict[intent](parameters, session_id)
        else:
            return JSONResponse(content={"fulfillmentText": "Intent not recognized."}, status_code=400)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return JSONResponse(content={"fulfillmentText": f"Internal Server Error: {e}"}, status_code=500)

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unexpected error: {exc}")
    return JSONResponse(content={"fulfillmentText": f"Internal Server Error: {exc}"}, status_code=500)
