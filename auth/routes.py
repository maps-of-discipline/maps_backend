from flask import Blueprint, Response, jsonify, request
from auth.enum import PermissionsEnum as p
from auth import require
from auth.models import Users

router = Blueprint("auth", __name__, url_prefix="/auth")


@router.route("/test")
@require()
def test() -> Response:
    return jsonify({"res": "ok"})


@router.route("/test1")
@require()
def test1(authenticated_user: Users) -> Response:
    return jsonify({"res": "ok", "user_email": authenticated_user.email})


@router.route("/test2")
@require(
    (p.canEditAnyFaculty, p.canEditOwnFaculty),
)
def test2(user_with_one_of_permissions: Users) -> Response:
    return jsonify({"res": "ok"})


@router.route("/test3")
@require(p.canEditAnyFaculty, p.canEditOwnMap)
def test3(user_with_permission: Users) -> Response:
    return jsonify({"res": "ok"})


@router.route("/test4")
@require(
    p.canEditOwnMap,
    p.canEditOwnFaculty,
)
def test4(user_with_combined_permissions: Users) -> Response:
    return jsonify({"res": "ok"})
