from botocore.exceptions import ClientError
import pytest

from app.services.storage import s3
from app.core.exceptions import VividGenError


def test_delete_object_rejects_keys_outside_v2_prefixes():
    with pytest.raises(VividGenError, match="outside the V2 storage prefixes"):
        s3.delete_object("private/user-object.txt")


def test_delete_object_surfaces_access_denied(monkeypatch):
    def denied(**_kwargs):
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "denied"}}, "DeleteObject")

    monkeypatch.setattr(s3._client, "delete_object", denied)
    with pytest.raises(ClientError) as error:
        s3.delete_object("uploads/user/probe.txt")
    assert error.value.response["Error"]["Code"] == "AccessDenied"
