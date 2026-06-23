import json
from enum import unique, Enum

import jwt
from django.db import models
from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods

from backend import settings

@unique
class ErrorCode(Enum):
    """
    api error code enumeration
    """
    SUCCESS_CODE = 200_00
    BAD_REQUEST_ERROR = 400_00
    FILE_WRITE_ERROR = 400_01
    INVALID_REQUEST_ARGS = 400_02
    INVALID_REQUEST_ARGUMENT_ERROR = 400_03
    NOT_FOUND_ERROR = 404_00
    ITEM_NOT_FOUND_ERROR = 404_01
    ITEM_ALREADY_EXIST_ERROR = 404_02
    ROS_CONNECT_FAILED = 500_01

def _api_response(success, data) -> dict:
    return {'success': success, 'data': data}

def success_api_response(data=None) -> dict:
    """
    wrap a success response dict obj
    :param data: requested data
    :return: an api response dictionary
    """
    if data is None:
        data = {"success": True}
    return _api_response(True, data)

def failed_api_response(code, error_msg=None) -> dict:
    """
    wrap an failed response dict obj
    :param code: error code, refers to ErrorCode, can be an integer or a str (error name)
    :param error_msg: external error information
    :return: an api response dictionary
    """
    if isinstance(code, str):
        code = ErrorCode[code]
    elif isinstance(code, int):
        code = ErrorCode(code)
    if error_msg is None:
        error_msg = str(code)
    else:
        error_msg = str(code) + ': ' + error_msg
    status_code = code.value // 100
    detailed_code = code.value
    return _api_response(
        success=False,
        data={
            'code': status_code,
            'detailed_error_code': detailed_code,
            'error_msg': error_msg
        })

def response_wrapper(func):
    """
    decorate a given api-function, parse its return value from a dict to a HttpResponse
    :param func: an api-function
    :return: wrapped function
    """

    def _inner(*args, **kwargs):
        _response = func(*args, **kwargs)
        if isinstance(_response, dict):
            resp = JsonResponse(_response)
            if not _response.get('success', True):
                status_code = _response.get('data', {}).get('code', 500)
                resp.status_code = status_code
            return resp
        return _response

    return _inner

def validate_request(func):
    """
    decorator to validate request with func
    :param func: check function
    :return: wrapped function
    """

    def decorator(function):
        def wrapper(request: HttpRequest, *args, **kwargs):
            if func(request):
                return function(request, *args, **kwargs)
            return failed_api_response(ErrorCode.INVALID_REQUEST_ARGUMENT_ERROR, "非法请求")

        return wrapper

    return decorator

def parse_data(request: HttpRequest):
    """
    parse request body and return a dict
    :param request: HttpRequest
    :return: request body dict if success else None
    """
    try:
        return json.loads(request.body.decode())
    except json.JSONDecodeError:
        return None