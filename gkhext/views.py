# -*- coding: utf-8 -*-
#
# Copyright (C) 2021 GEO Secretariat.
#
# geo-knowledge-hub-ext is free software; you can redistribute it and/or
# modify it under the terms of the MIT License; see LICENSE file for more
# details.

"""GEO Knowledge Hub extension for InvenioRDM"""

from flask import g

from pydash import py_
from typing import Dict

from elasticsearch_dsl.utils import AttrDict
from flask import (
    request,
    url_for,
    redirect,
    Blueprint,
    current_app,
    render_template,
)
from flask_babelex import lazy_gettext as _
from flask_login import login_required
from flask_mail import Message
from flask_menu import current_menu
from invenio_app_rdm.records_ui.views.decorators import (
    pass_record_files,
    pass_draft, pass_draft_files, pass_record_or_draft,
)
from invenio_app_rdm.records_ui.views.deposits import get_form_config, get_search_url, new_record
from invenio_rdm_records.resources.serializers import UIJSONSerializer
from pydash import py_

from .controller import (
    get_related_resources_metadata,
    current_user_invenio_profile
)
from .forms import RequestAccessForm
from .records.identifiers import related_identifiers_url_by_scheme
from .search import FrontpageRecordsSearch
from .security.actions import secretariat_permission


def generate_ui_bp(flask_app):
    routes = flask_app.config.get("GKH_ROUTES")

    bp = Blueprint(
        'geokhb_theme',
        __name__,
        template_folder="templates",
    )

    @flask_app.context_processor
    def define_user_profile():
        is_knowledge_provider = False
        if "identity" in g:
            is_knowledge_provider = kprovider_permission.can()

        return {"is_knowledge_provider": is_knowledge_provider,
                "current_user_profile": current_user_invenio_profile()}

    @bp.before_app_first_request
    def init_menu():
        """Initialize menu before first request."""
        item = current_menu.submenu("main.deposit")
        item.register(
            "invenio_app_rdm_records.deposit_search", _("Uploads"), order=1)

        item = current_menu.submenu('plus.deposit-resource')
        item.register(
            'invenio_app_rdm_records.deposit_create',
            _('Knowledge <b>Resource</b>'),
            endpoint_arguments_constructor=(lambda: dict(type="resource")),
            order=2
        )

        item = current_menu.submenu('plus.deposit')
        item.register(
            'invenio_app_rdm_records.deposit_create',
            _('Knowledge <b>Package</b>'),
            endpoint_arguments_constructor=(lambda: dict(type="knowledge")),
            order=1
        )

    @bp.app_template_filter("make_dict_like")
    def make_dict_like(value: str, key: str) -> Dict[str, str]:
        """Convert the value to a dict like structure.
        in the form of a key -> value pair.
        """
        return {key: value}

    @bp.app_template_filter("cast_to_dict")
    def cast_to_dict(attr_dict):
        """Return the dict structure of AttrDict variable."""
        return AttrDict.to_dict(attr_dict)

    return bp


#
# New Geo Knowledge Pages
#
@pass_record_or_draft
@pass_record_files
def record_detail_page_render(record=None, files=None, pid_value=None, is_preview=False):
    """Function to render landing page (Record detail page)
    """

    files_dict = None if files is None else files.to_dict()
    related_records_informations = get_related_resources_metadata(record.to_dict()["metadata"])

    related_identifiers = py_.get(record.data, "metadata.related_identifiers", [])
    related_identifiers = related_identifiers_url_by_scheme(related_identifiers)

    # removing all related resource that is a knowledge resource
    related_identifiers = py_.filter(
        related_identifiers, lambda x: x["identifier"].split("/")[-1] not in py_.map(
            related_records_informations, lambda y: y["id"]
        )
    )

    return render_template(
        "gkhext/records/detail.html",
        pid=pid_value,
        files=files_dict,
        is_preview=is_preview,
        related_identifiers=related_identifiers,
        related_records_informations=related_records_informations,
        record=UIJSONSerializer().serialize_object_to_dict(record.to_dict()),

        permissions=record.has_permissions_to(['edit', 'new_version', 'manage',
                                               'update_draft', 'read_files'])
    )


#
# Communities pages
#
def communities_frontpage():
    """Communities index page."""
    return render_template(
        "gkhext/communities/frontpage.html",
        is_user_allowed_to_create_new_community=secretariat_permission.can()
    )


def front_page():
    """Render the front-page"""
    latest_records = FrontpageRecordsSearch()[:3].sort("-created").execute()
    latest_records = [UIJSONSerializer().serialize_object_to_dict(r.to_dict()) for r in latest_records]

    is_knowledge_provider = kprovider_permission.can()

    return render_template(
        "gkhext/frontpage.html",
        latest_records=latest_records,
        is_knowledge_provider=is_knowledge_provider
    )


def about_page():
    """Render the about page"""
    return render_template("gkhext/about.html")


def discover_page():
    """Render the discover page"""
    return render_template("gkhext/discover.html")


def contribute_page():
    """Render the contribute page"""
    return render_template("gkhext/contribute.html")


def engage_page():
    """Render the engagement page"""
    return render_template("gkhext/engage.html")


#
# Forms views
#
def request_access_view():
    """Function to render Request Access view"""

    form = RequestAccessForm()
    form.process(request.form)

    if form.validate_on_submit():
        message = Message(
            f"Geo Knowledge Hub Registration",
            recipients=[
                current_app.config.get(
                    "GEO_KNOWLEDGE_HUB_EXT_DEFAULT_MAIL_RECEIVER"
                ),
                form.email.data
            ],
            body=f"Thank you {form.name.data} for your subscription"
        )

        current_app.extensions["mail"].send(message)
        return redirect(url_for("request_access_page"))
    return render_template(
        "gkhext/request_access.html",
        form=form,
        template="form-template"
    )


"""Overwriting pages for adding specific function requirements"""

#
# Deposit Pages
#

from invenio_app_rdm.records_ui.views.deposits import (
    deposit_create,
    deposit_edit
)

from .security.actions import kprovider_permission


@kprovider_permission.require(http_exception=403)
def deposit_create_permissioned():
    return deposit_create()


@kprovider_permission.require(http_exception=403)
def deposit_edit_permissioned(pid_value):
    return deposit_edit(pid_value=pid_value)


@login_required
@kprovider_permission.require(http_exception=403)
def deposit_search():
    """List of user deposits page."""
    return render_template(
        "gkhext/records/search_deposit.html",
        searchbar_config=dict(searchUrl=get_search_url())
    )


@login_required
@kprovider_permission.require(http_exception=403)
def new_deposit_page():
    """Deposit page"""
    from flask import request

    valid_types = {
        "knowledge": {
            "id": "knowledge",
            "title": {
                "en": "Knowledge Package"
            }
        }
    }

    nrecord = new_record()
    record_type = request.args.get("type")

    if record_type in valid_types and record_type == "knowledge":
        nrecord["metadata"]["resource_type"] = valid_types.get(record_type)

    return render_template(
        "gkhext/records/deposit.html",
        forms_config=get_form_config(createUrl=("/api/records")),
        searchbar_config=dict(searchUrl=get_search_url()),
        record=nrecord,
        files=dict(
            default_preview=None, entries=[], links={}
        ), )


@login_required
@kprovider_permission.require(http_exception=403)
@pass_draft
@pass_draft_files
def geo_deposit_edit_new(draft=None, draft_files=None, pid_value=None):
    """Edit an existing deposit."""
    serializer = UIJSONSerializer()
    record = serializer.serialize_object_to_dict(draft.to_dict())

    return render_template(
        "gkhext/records/deposit.html",
        forms_config=get_form_config(apiUrl=f"/api/records/{pid_value}/draft"),
        record=record,
        files=draft_files.to_dict(),
        searchbar_config=dict(searchUrl=get_search_url()),
        permissions=draft.has_permissions_to(['new_version'])
    )


deposit_views = [
    {
        "endpoint": "/uploads",
        "name": "geo_deposit_search",
        "func": deposit_search
    },
    {
        "endpoint": "/uploads/new",
        "name": "geo_deposit_create",
        "func": new_deposit_page
    },
    {
        "endpoint": "/uploads/<pid_value>",
        "name": "geo_deposit_edit",
        "func": geo_deposit_edit_new
    }
]

#
# Communities pages
#
from invenio_communities.views.communities import communities_new


@secretariat_permission.require(http_exception=403)
def communities_new_permissioned():
    return communities_new()


communities_views = [
    {
        "endpoint": "/communities/new",
        "name": "geo_communities_new",
        "func": communities_new_permissioned
    },
]
