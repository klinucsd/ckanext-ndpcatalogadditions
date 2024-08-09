import random
import string
import traceback

import ckan.model as model
import ckan.logic as logic
from ckan.plugins import toolkit
from ckanext.ndp.keycloak_token import get_user_info
from flask import request, jsonify


def generate_random_password(length=32):
    characters = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choice(characters) for i in range(length))


def get_or_create_user():

    # Get the Authorization header
    auth_header = request.headers.get('Authorization')

    # Extract the Bearer Token if the header exists
    if auth_header and auth_header.startswith('Bearer '):
        bearer_token = auth_header[len('Bearer '):]
    else:
        raise ValueError('Missing or invalid KeyCloak token')

    user_info = get_user_info(bearer_token)
    username = user_info['username'].replace('.', '_').replace('@', '_')
    user = model.User.get(username)
    if not user:
        # Create a new user
        user = model.User(name=username, email=user_info['email'])
        user.fullname = user_info['name']
        user.password = generate_random_password()
        user.state = model.State.ACTIVE
        model.Session.add(user)
        model.Session.commit()
    return user


def process_user_and_organization(user, org_name):
    organization = model.Group.get(org_name)
    if not organization:
        # Create the organization object
        organization = model.Group(name=org_name,
                                   title=org_name,
                                   description="This is the organization description.",
                                   type='organization',
                                   is_organization=True)
        model.Session.add(organization)
        model.Session.commit()        

    member = model.Member(group=organization, table_id=user.id, table_name='user', capacity='editor')
    model.Session.add(member)
    model.Session.commit()   
    return organization
    

def create_package():
    if request.method == 'POST':
        try:
            user = get_or_create_user()
            dataset_dict = request.get_json()
            if 'owner_org' in dataset_dict.keys():
                process_user_and_organization(user, dataset_dict['owner_org'])
            context = {'user': user.name}
            dataset = logic.get_action('package_create')(context, dataset_dict)                
            return dataset
        except Exception as e:
            traceback.print_exc()
            return f'Error: {str(e)}', 401

    return "Method not allowed", 405  # For unsupported methods


def update_package():
    if request.method == 'POST':
        try:
            user = get_or_create_user()
            dataset_dict = request.get_json()
            if 'owner_org' in dataset_dict.keys():
                process_user_and_organization(user, dataset_dict['owner_org'])
            context = {'user': user.name}
            result = logic.get_action('package_update')(context, dataset_dict)
            return result
        except Exception as e:
            traceback.print_exc()
            return f'Error: {str(e)}', 401

    return "Method not allowed", 405  # For unsupported methods


def delete_package():
    if request.method == 'POST':
        try:
            user = get_or_create_user()
            dataset_dict = request.get_json()            
            context = {'user': user.id}
            logic.get_action('package_delete')(context, dataset_dict)
            return f"The package '{dataset_dict['id']}' is deleted."
        except Exception as e:
            traceback.print_exc()
            return f'Error: {str(e)}', 401

    return "Method not allowed", 405  # For unsupported methods


def purge_package():
    if request.method == 'POST':
        try:
            user = get_or_create_user()
            dataset_dict = request.get_json()
            context = {'user': user.id}
            result = logic.get_action('dataset_purge')(context, dataset_dict)
            return f"The package '{dataset_dict['id']}' is purged."
        except logic.NotAuthorized:
            return "Not authorized to purge this dataset", 401            
        except Exception as e:
            traceback.print_exc()
            return f'Error: {str(e)}', 401

    return "Method not allowed", 405  # For unsupported methods


def list_my_packages():
    if request.method == 'POST' or request.method == 'GET':
        try:
            user = get_or_create_user()
            context = {'user': user.id}
            search_dict = {
                'q': f'creator_user_id:{user.id}',
                'rows': 1000  
            }
            result = logic.get_action('package_search')(context, search_dict)
            return result
        except Exception as e:
            traceback.print_exc()
            return f'Error: {str(e)}', 401

    return "Method not allowed", 405  # For unsupported methods

