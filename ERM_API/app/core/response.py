from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder


# Standardized response format for success and error responses
def success_response(data=None, message="Success", status_code=200):
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder({
            "data": data,
            "Error": {
                "Error": False,
                "Error_message": message,
                "Error_Code": status_code
            }
        })
    )


# Standardized response format for error responses
def error_response(message="Error", status_code=400):
    return JSONResponse(
        status_code=status_code,
        content={
            "data": None,
            "Error": {
                "Error": True,
                "Error_message": message,
                "Error_Code": status_code
            }
        }
    )