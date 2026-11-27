from rivex import APIStatus, HTTPMethod, HTTPStatus, StatusCode, status


def test_http_method_enum_values():
    assert HTTPMethod.GET == "GET"
    assert HTTPMethod.POST == "POST"


def test_api_status_enum_values():
    assert APIStatus.OK == 200
    assert APIStatus.CREATED == 201
    assert StatusCode is APIStatus


def test_status_compatibility_object():
    assert status.HTTP_200_OK == APIStatus.OK
    assert status.HTTP_404_NOT_FOUND == 404


def test_http_status_constants():
    assert HTTPStatus.OK == 200
    assert HTTPStatus.NOT_FOUND == 404
    assert HTTPStatus.INTERNAL_SERVER_ERROR == 500
