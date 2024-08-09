import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
from flask import Blueprint
from ckanext.ndp.controller import create_package, update_package, delete_package, purge_package, list_my_packages


class NdpPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IBlueprint)    
    
    # IConfigurer
    def update_config(self, config_):
        toolkit.add_template_directory(config_, "templates")
        toolkit.add_public_directory(config_, "public")
        toolkit.add_resource("assets", "ndpcatalogadditions")

    def get_blueprint(self):
        blueprint = Blueprint(self.name, self.__module__)

        blueprint.add_url_rule(
            u'/ndp/package_create',
            u'create_package',
            create_package,
            methods=['POST']
        )

        blueprint.add_url_rule(
            u'/ndp/package_update',
            u'update_package',
            update_package,
            methods=['POST']
        )

        blueprint.add_url_rule(
            u'/ndp/package_delete',
            u'delete_package',
            delete_package,
            methods=['POST']
        )
        
        blueprint.add_url_rule(
            u'/ndp/package_purge',
            u'purge_package',
            purge_package,
            methods=['POST']
        )

        blueprint.add_url_rule(
            u'/ndp/my_package_list',
            u'my_package_list',
            list_my_packages,
            methods=['GET', 'POST']
        )

        return blueprint
