from flask import Request, jsonify, Response
import werkzeug.exceptions as http_exceptions
# !
from maps.models import db
from administration.base import BaseAdminView


class SimpleAdminView(BaseAdminView):
    model: type
    fields: list[tuple[str, str]] = []

    def _get_model_headers(self) -> list[dict]:
        headers = []

        for el in self.fields:
            field, title = el
            headers.append({"value": field, "text": title})

        return headers

    def _serialize(self, model_instance):
        selected_columns = [el[0] for el in self.fields]
        data = {}

        for column in self.model.__table__.columns:
            if column.name in selected_columns:
                data.update({column.name: getattr(model_instance, column.name)})

        return data

    def list(self, request, id):
        response = {"headers": self._get_model_headers(), "data": []}

        for el in self.model.query.all():
            response["data"].append(self._serialize(el))

        return response

    def detail(self, request, id):
        model_instance = self.model.query.get(id)

        if not model_instance:
            raise http_exceptions.NotFound()

        return model_instance.as_dict()
    
    def post(self, request: Request, id: int):
        data = request.get_json()
        model_instanse = self.model()

        for field, value in data.items():
            if field in self.model.__dict__:
                model_instanse.__setattr__(field, value)

        db.session.add(model_instanse)
        db.session.commit()

        return {"id": model_instanse._sa_instance_state.key[1][0]}

    def put(self, request, id):
        data = request.get_json()
        model_instanse = self.model.query.get(id)

        if not model_instanse:
            raise http_exceptions.NotFound()

        for field, value in data.items():
            if field in self.model.__dict__:
                model_instanse.__setattr__(field, value)

        db.session.add(model_instanse)
        db.session.commit()

        return {"result": "ok"}

    def delete(self, request, id):
        if not id:
            raise http_exceptions.BadRequest()

        model_instanse = self.model.query.get(id)

        if not model_instanse:
            raise http_exceptions.NotFound()

        db.session.delete(model_instanse)
        db.session.commit()

        return {"result": "ok"}
