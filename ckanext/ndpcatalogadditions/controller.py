
import os
import random
import string
import traceback
import requests
import json

import ckan.model as model
import ckan.logic as logic
from ckan.plugins import toolkit
from ckan.authz import is_sysadmin
from ckan.lib.munge import munge_title_to_name
from ckanext.ndp.keycloak_token import get_user_info
from flask import request, jsonify


server_url = os.getenv('CKANEXT__KEYCLOAK__REDIRECT_URI')
ckan_url = server_url.replace('/user/sso_login', '')

api_key = os.getenv('CKANEXT__NDPCATALOGADDITIONS__API_KEY')

headers = {
    'X-CKAN-API-Key': api_key,
    'Content-Type': 'application/json'
}


def generate_random_password(length=32):
    characters = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choice(characters) for i in range(length))


def is_reviewer(username):
    return username in [ "klin_sdsc_edu", "segurvich_sdsc_edu", "kbolaughlin_ucsd_edu", "jjl053_ucsd_edu", "pkarmakar_ucsd_edu" ] 


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
    organization = model.Group.get(munge_title_to_name(org_name))
    if not organization:
        # Create the organization object
        organization = model.Group(name=munge_title_to_name(org_name),
                                   title=org_name,
                                   description="Created by admin when creating a new dataset",
                                   type='organization',
                                   is_organization=True)
        model.Session.add(organization)
        model.Session.commit()        

    member = model.Member(group=organization, table_id=user.id, table_name='user', capacity='editor')
    model.Session.add(member)
    model.Session.commit()   
    return organization
    

def get_or_create_remote_user(username, email, fullname):
    user_show_url = f'{ckan_url}/api/3/action/user_show'
    response = requests.get(user_show_url, headers=headers, params={'id': username})
    
    if response.status_code == 200:
        user_info = response.json()['result']
        return user_info
    
    elif "Not Found" in response.text:
        # create a new user account
        api_url = f'{ckan_url}/api/3/action/user_create'

        # User information
        data = {
            'name': username,
            'email': email,
            'fullname': fullname,
            'password': generate_random_password(),    
        }

        # Make the API request
        response = requests.post(api_url, data=json.dumps(data), headers=headers)

        # Check the response
        if response.status_code == 200:
            new_user = response.json()['result']
            return new_user
        else:
            raise ValueError(f"Error creating user: {response.text}")
    else:
        raise ValueError(f"Failed to retrieve user info: {response.text}")


def process_remote_user_and_organization(remote_user, organization):   
    data = { 'id': organization.name }
    response = requests.post(f'{ckan_url}/api/3/action/organization_show', headers=headers, json=data)
    if response.status_code == 200:
        remote_organization = response.json()['result']
    else:
        # create a new organization in the remote CKAN
        org_data = {
            "name": organization.name,
            "title": organization.title,
            "description": organization.description
        }
        response = requests.post(f'{ckan_url}/api/3/action/organization_create', headers=headers, json=org_data)
        if response.status_code == 200:
            remote_organization = response.json()['result']
        else:
            raise ValueError(f"Failed to create organization: {response.text}")
    
    # add the user as an editor to the remote organization
    member_data = {
        'id': remote_organization['id'],
        'username': remote_user['name'],
        'role': 'editor'
    }
    response = requests.post(f'{ckan_url}/api/3/action/organization_member_create', headers=headers, json=member_data)
    if response.status_code != 200:
        raise Value(f"Failed to add user to organization: {response.text}")

    return remote_organization
    

def create_api_token(username):
    api_url = f'{ckan_url}/api/3/action/api_token_create'
    data = {
        'name': 'dataset_token',
        'user': username
    }
    response = requests.post(api_url, data=json.dumps(data), headers=headers)
    if response.status_code == 200:
        new_token = response.json()['result']['token']
        return new_token
    else:
        raise ValueError(f"Error creating API token: {response.text}")


def delete_api_token(token):
    api_url = f'{ckan_url}/api/3/action/api_token_revoke'
    data = {
        'token': token,
    }
    response = requests.post(api_url, data=json.dumps(data), headers=headers)
    if response.status_code != 200:
        raise ValueError(f"Error creating API token: {response.text}")
    

def save_remote_dataset(remote_user, dataset):
    token = create_api_token(remote_user['name'])
    try:
        api_url = f"{ckan_url}/api/3/action/package_create"
        response = requests.post(api_url, data=json.dumps(dataset), headers=headers)
        if response.status_code == 200:
            created_package = response.json()['result']
            return created_package
        else:
            raise ValueError(f"Failed to create dataset: {response.text}   {json.dumps(dataset, indent=4)}")
    finally:
        delete_api_token(token)

    
def create_package():
    if request.method == 'POST':
        try:
            user = get_or_create_user()
            dataset_dict = request.get_json()
            if 'owner_org' in dataset_dict.keys():
                organization = process_user_and_organization(user, dataset_dict['owner_org'])
                dataset_dict['owner_org'] = organization.name
            context = {'user': user.name}
            dataset = logic.get_action('package_create')(context, dataset_dict)                
            return dataset
        except Exception as e:
            return f'Error: {str(e)}', 401

    return "Method not allowed", 405  # For unsupported methods


def update_package():
    if request.method == 'POST':
        try:
            user = get_or_create_user()
            dataset_dict = request.get_json()
            if 'owner_org' in dataset_dict.keys():
                organization = process_user_and_organization(user, dataset_dict['owner_org'])
                dataset_dict['owner_org'] = organization.name
            context = {'user': user.name}
            result = logic.get_action('package_update')(context, dataset_dict)
            return result
        except Exception as e:
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
            return f'Error: {str(e)}', 401

    return "Method not allowed", 405  # For unsupported methods


def purge_package():
    if request.method == 'POST':
        try:
            user = get_or_create_user()
            dataset_dict = request.get_json()
            context = {'user': user.id}
            logic.get_action('dataset_purge')(context, dataset_dict)
            return f"The package '{dataset_dict['id']}' is purged."
        except logic.NotAuthorized:
            return "Not authorized to purge this dataset", 401            
        except Exception as e:
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
            return f'Error: {str(e)}', 401

    return "Method not allowed", 405  # For unsupported methods


def approve_package():
    if request.method == 'POST':
        try:
            user = get_or_create_user()
            dataset_dict = request.get_json()

            if not user.sysadmin and not is_reviewer(user.name):
                return "Not authorized to approve this dataset.", 401
    
            # actions in the production catalog
            #    1. find the creator and the owner_org of the dataset
            #    2. create a user for the creator if doesn't exist 
            #    3. create a organization for the owner_org if doesn't exists 
            #    4  add the creator as an editor to the owner_org
            #    5. create the dataset

            # get the dataset with ignore_auth. Note that the reviewer may not has the permission to view this package if it is private
            context = {'ignore_auth': True}
            dataset = logic.get_action('package_show')(context, {'id': dataset_dict['id']})
            if dataset['state'] == 'deleted':
                return f"The dataset '{dataset['name']}' was already deleted. Can not approve it.", 401
                
            creator_user_id = dataset['creator_user_id']

            # create a remote user if doesn't exist
            creator = model.User.get(creator_user_id)
            creator_name = creator.name
            email = creator.email
            fullname = creator.fullname
            remote_user = get_or_create_remote_user(creator_name, email, fullname)

            # create a remote organization if doesn't exist and add the remote user as an editor
            remote_organization = None
            if 'owner_org' in dataset.keys():
                organization = model.Group.get(dataset['owner_org'])
                remote_organization = process_remote_user_and_organization(remote_user, organization)

            # delete dataset id
            del dataset['id']
            
            # delete the creator_user_id
            del dataset['creator_user_id'] 

            # change the owner_org id
            if remote_organization:
                dataset['owner_org'] = remote_organization['id']
                del dataset['organization']

            # delete package_id from each resource
            if 'resources' in dataset.keys():
                for resource in dataset['resources']:
                    del resource['package_id']
                    del resource['id']
                    
            # save the dataset to the remote CKAN
            remote_dataset = save_remote_dataset(remote_user, dataset)
                
            # action in the local catalog
            #    1. delete the dataset
            
            # delete this dataset with ignore_auth context
            logic.get_action('package_delete')(context, dataset_dict)

            # return f"The package '{dataset['name']}' is moved to the production catalog."
            return remote_dataset
        
        except logic.NotAuthorized:
            traceback.print_exc()
            return "Not authorized to approve this dataset.", 401            
        except Exception as e:
            traceback.print_exc()
            return f'Error: {str(e)}', 401

    return "Method not allowed", 405  # For unsupported methods


def reject_package():
    if request.method == 'POST':
        try:
            user = get_or_create_user()
            dataset_dict = request.get_json()

            if not user.sysadmin and not is_reviewer(user.name):
                return "Not authorized to approve this dataset.", 401
            
            # Note that the reviewer may not has the permission to view this package if it is private
            context = {'ignore_auth': True}
            logic.get_action('dataset_purge')(context, {'id': dataset_dict['id']})

            return f"The dataset '{dataset_dict['id']}' is rejected and purged."
        except logic.NotAuthorized:
            traceback.print_exc()
            return "Not authorized to approve this dataset.", 401            
        except Exception as e:
            traceback.print_exc()
            return f'Error: {str(e)}', 401

    return "Method not allowed", 405  # For unsupported methods

