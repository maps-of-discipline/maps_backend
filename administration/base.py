from flask import jsonify, Request, Response
import werkzeug.exceptions as http_exceptions


class BaseAdminView:
    def handle_request(self, request: Request, id: int | None = None) -> Response:
        result = None

        try:
            result = self._map_reqeust_method(request, id)
        except http_exceptions.NotFound:
            return jsonify({"result": "not found"}), 404
        except http_exceptions.BadRequest as e:
            return jsonify({"result": "bad request", 'message': str(e)}), 400
        
        return jsonify(result), 200
    
    def _map_reqeust_method(self, request: Request, id: int | None = None) -> list | dict:
        method = request.method.lower()
        if method == 'get':
            method = 'detail' if id else 'list'

        handler = getattr(self, method)
        return handler(request, id) 


    