import ckan.plugins.toolkit as tk


@tk.auth_allow_anonymous_access
def ndpcatalogadditions_get_sum(context, data_dict):
    return {"success": True}


def get_auth_functions():
    return {
        "ndpcatalogadditions_get_sum": ndpcatalogadditions_get_sum,
    }
