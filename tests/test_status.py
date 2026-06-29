from rivex import APIStatus, HTTPMethod, HTTPStatus, StatusCode, status


def test_http_method_enum_values():
    assert HTTPMethod.GET == "GET"
    assert HTTPMethod.POST.value == "POST"


def test_api_status_enum_values():
    assert APIStatus.OK == 200
    assert APIStatus.CREATED.value == 201
    assert HTTPStatus is APIStatus
    assert StatusCode is APIStatus


def test_status_compatibility_object():
    assert status.HTTP_200_OK == APIStatus.OK
    assert status.HTTP_404_NOT_FOUND == 404
