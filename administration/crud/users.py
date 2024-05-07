from flask import Request, jsonify, Response
import werkzeug.exceptions as http_exceptions

from auth.models import Roles, Users
from administration.base import BaseAdminView
from maps.models import db, SprBranch, SprFaculty

class UserCrudView(BaseAdminView):
    model = Users

    def _serialize_detail(self, user_instance: Users) -> dict: 
        data = user_instance.as_dict()
        data['roles'] = [role.as_dict() for role in user_instance.roles]
        data['faculties'] = [faculty.as_dict() for faculty in user_instance.faculties]
        data['department'] = user_instance.department.as_dict() if user_instance.department else None

        return data


    def detail(self, request: Request, id: int | None) -> dict:
        user_instance: Users = Users.query.get(id)
        
        if not user_instance: 
            raise http_exceptions.NotFound()
        
        return self._serialize_detail(user_instance)
    

    def list(self, request: Request, id: int | None) -> dict: 
        headers = [ 
            {'value': 'id_user',    'text': 'ИД'}, 
            {'value': 'login',      'text': 'Логин'}, 
            {'value': 'email',      'text': 'Email'}, 
            {'value': 'roles',      'text': 'Роли'}, 
            {'value': 'faculties',  'text': 'Факультеты'}, 
            {'value': 'department', 'text': 'Кафедра'}, 
        ] 
        
        data = []
        for user in Users.query.all():
            user: Users
            data.append({
                "id_user": user.id_user, 
                "login": user.login, 
                "roles": ', '.join([role.name_role for role in user.roles]),
                "faculties": ', '.join([fac.name_faculty for fac in user.faculties]),
                "department": user.department.name_department if user.department else None
            })

        return {"headers": headers, "data": data}

    def post(self, request: Request, id: int | None):
        """
            Create User method handler
        """

        data = request.get_json()

        for key in ['login', 'email', 'faculties', 'roles']:
            if key not in data or not data[key]:
                raise http_exceptions.BadRequest(f'{key} have be provided.')

        new_user = Users()
        new_user.login = data['login']
        new_user.email = data['email']
        new_user.set_password(data['password'])
        
        new_user.department_id = data['department_id']

        faculty_instances = SprFaculty.query.filter(SprFaculty.id_faculty.in_(data['faculties'])).all()
        role_instances = Roles.query.filter(Roles.id_role.in_(data['roles'])).all()

        new_user.faculties = faculty_instances
        new_user.roles = role_instances

        db.session.add(new_user)
        db.session.commit()

        return self._serialize_detail(new_user)
    
    
    def put(self, request: Request, id: int | None):
        """
            Edit User method handler
        """

        data = request.get_json()

        for key in ['login', 'email', 'faculties', 'roles']:
            if key not in data or not data[key]:
                raise http_exceptions.BadRequest(f'{key} have be provided.')

        user_instance = Users.query.get(id)
        if not user_instance: 
            raise http_exceptions.NotFound()

        user_instance.login = data['login']
        user_instance.email = data['email']
        user_instance.set_password(data['password'])
        
        user_instance.department_id = data['department_id']

        faculty_instances = SprFaculty.query.filter(SprFaculty.id_faculty.in_(data['faculties'])).all()
        role_instances = Roles.query.filter(Roles.id_role.in_(data['roles'])).all()

        user_instance.faculties = faculty_instances
        user_instance.roles = role_instances

        db.session.add(user_instance)
        db.session.commit()

        return self._serialize_detail(user_instance)


    def delete(self, request: Request, id: int | None) -> dict:
        user_instance: Users = Users.query.get(id)
        
        if not user_instance: 
            raise http_exceptions.NotFound()
        
        db.sesstion.delete(user_instance)
        db.session.commit()
        return {'resutl': 'ok'}