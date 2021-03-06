# -*- coding: utf-8 -*-
from Products.Five import BrowserView
from zope.component import getUtility

from zope import schema
from zope.schema.vocabulary import SimpleVocabulary

from plone.app.controlpanel.form import ControlPanelForm

from plone.fieldsets.fieldsets import FormFieldsets
from plone.fieldsets.form import FieldsetsEditForm

from zope.component import adapts
from zope.interface import implements
from zope.interface import Interface

from Products.CMFDefault.formlib.schema import SchemaAdapterBase
from Products.CMFPlone.interfaces import IPloneSiteRoot

from zope.formlib import form
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile

from interfaces import IFacebookControlPanel

from collective.facebook.accounts import _
from plone.registry.interfaces import IRegistry

from plone.i18n.normalizer.interfaces import IIDNormalizer

from collective.facebook.accounts.config import PROJECTNAME

import json
import urllib
from datetime import datetime, timedelta
import DateTime
import logging

logger = logging.getLogger(PROJECTNAME)

non_revocable_permissions = ['user_about_me',
                             'friends_about_me',
                             'user_activities',
                             'friends_activities',
                             'user_birthday',
                             'friends_birthday',
                             'user_checkins',
                             'friends_checkins',
                             'user_education_history',
                             'friends_education_history',
                             'user_events',
                             'friends_events',
                             'user_groups',
                             'friends_groups',
                             'user_hometown',
                             'friends_hometown',
                             'user_interests',
                             'friends_interests',
                             'user_likes',
                             'friends_likes',
                             'user_location',
                             'friends_location',
                             'user_notes',
                             'friends_notes',
                             'user_online_presence',
                             'friends_online_presence',
                             'user_photo_video_tags',
                             'friends_photo_video_tags',
                             'user_photos',
                             'friends_photos',
                             'user_questions',
                             'friends_questions',
                             'user_relationships',
                             'friends_relationships',
                             'user_relationship_details',
                             'friends_relationship_details',
                             'user_religion_politics',
                             'friends_religion_politics',
                             'user_status',
                             'friends_status',
                             'user_videos',
                             'friends_videos',
                             'user_website',
                             'friends_website',
                             'user_work_history',
                             'friends_work_history',
                             'email']

revocable_permissions = ['read_friendlists',
                         'read_insights',
                         'manage_pages',
                         'read_mailbox',
                         'read_requests',
                         'read_stream',
                         'xmpp_login',
                         'ads_management',
                         'create_event',
                         'manage_friendlists',
                         'manage_notifications',
                         'offline_access',
                         'publish_checkins',
                         'publish_stream',
                         'rsvp_event',
                         'sms',
                         'publish_actions']


nonRevocableVocabulary = SimpleVocabulary.fromItems([(perm, perm) for perm in non_revocable_permissions])
revocableVocabulary = SimpleVocabulary.fromItems([(perm, perm) for perm in revocable_permissions])


class IFacebookUserSchema(Interface):
    """ Facebook App Config """
    non_r_perm = schema.List(title=_(u'Non revocable permissions'),
                             description=_(u"Choose which non revocable "
                                            "permissions to ask access to. "
                                            "Full explanation for each: "
                                            "https://developers.facebook.com"
                                            "/docs/reference/api/permissions/"),
                             required=False,
                             value_type = schema.Choice(vocabulary=nonRevocableVocabulary,),
                             )

    r_perm = schema.List(title=_(u'Revocable permissions'),
                         description=_(u"Choose which revocable permissions "
                                        "to ask access to. Full explanation "
                                        "for each: "
                                        "https://developers.facebook.com"
                                        "/docs/reference/api/permissions/"),
                         required=False,
                         value_type = schema.Choice(vocabulary=revocableVocabulary,),
                         )

    app_key = schema.TextLine(title=_(u'App ID/API Key'),
                              description=_(u"ID for your application. "
                                             "You need to create an app here: "
                                             "https://developers.facebook.com/"
                                             "apps"),
                              required=True)

    # I think this is not neccessary
    app_secret = schema.TextLine(title=_(u'App Secret'),
                                 description=_(u"Secret for your application. ( mandatory to get long life user token )"),
                                 required=False)

class IFacebookAppSchema(Interface):

    app_key2 = schema.TextLine(title=_(u'App ID/API Key'),
                              description=_(u"ID for your application. "
                                             "You need to create an app here: "
                                             "https://developers.facebook.com/"
                                             "apps"),
                              required=True)

    app_secret2 = schema.TextLine(title=_(u'App Secret'),
                                 description=_(u"Secret for your application."),
                                 required=True)

class IFacebookSchema(IFacebookUserSchema, IFacebookAppSchema):
    """
    """


class FacebookControlPanelAdapter(SchemaAdapterBase):

    adapts(IPloneSiteRoot)
    implements(IFacebookSchema)

    non_r_perm = ""
    r_perm = ""
    app_key = ""
    app_secret = ""
    app_key2 = ""
    app_secret2 = ""


class FacebookControlPanel(ControlPanelForm):
    """
    Facebook control panel view
    """

    implements(IFacebookControlPanel)

    template = ViewPageTemplateFile('./templates/facebook-control-panel.pt')
    label = _("Facebook setup")
    description = _("""Lets you configure several Facebook accounts""")

    auth_user = FormFieldsets(IFacebookUserSchema)
    auth_user.id = 'auth_user'
    auth_user.label = _(u'Authorize user')

    auth_app = FormFieldsets(IFacebookAppSchema)
    auth_app.id = 'auth_app'
    auth_app.label = _(u'Authorize app')

    form_fields = FormFieldsets(
                        auth_user,
                        auth_app
                        )

    request_user_auth = _(u"Request user auth")
    request_app_token = _(u"Authenticate app")

    def decodeParams(self,params):
        response = {}
        for param in params.split("&"):
            key, value = param.split("=")
            response[key] = value
        return response

    def __call__(self):
        if 'access_token' in self.request:
            logger.info("Got a request with a token !")

            token = self.request.get('access_token')
            type_token = ""
            logger.info("Token: %s"%token)

            if self.request.get('app_token'):
                url = "https://graph.facebook.com/app?access_token="
                type_token = "app_token"
            else:
                url = "https://graph.facebook.com/me?access_token="
                type_token = "user_token"

            expires = self.request.get('expires_in', '0')

            state = self.request.get("state")

            if type_token == "user_token" and len(state.split("|")) > 1:
                app_id, app_secret = state.split("|")
                url_extend = ("https://graph.facebook.com/oauth/access_token?" +
                              "grant_type=fb_exchange_token&" +
                              "client_id={app_id}&" +
                              "client_secret={app_secret}&" +
                              "fb_exchange_token={short_token}").format(app_id=app_id, app_secret=app_secret, short_token=token)

                response = urllib.urlopen(url_extend)
                params = self.decodeParams(response.read())
                token = params.get("access_token", token)

                logger.info("Long Live Token: %s" % token)
                expires = params.get("expires", expires)

            if expires != '0':
                date = datetime.now() + timedelta(seconds=int(expires))
                date = DateTime.DateTime(date)
            else:
                date = None

            logger.info("URL to open: %s" % (url + token))
            info = json.load(urllib.urlopen(url + token))
            name = info.get('name', 'no_name')
            id = info.get('id')

            registry = getUtility(IRegistry)
            accounts = registry['collective.facebook.accounts']
            if not accounts:
                accounts = {}

            logger.info("About to save data in the registry")
            logger.info("name: %s" % name)
            logger.info("access_token: %s" % token)
            logger.info("expires: %s" % date)

            others = json.load(urllib.urlopen("https://graph.facebook.com/" + id + "/accounts?access_token=" + token))
            
            for other in others.get("data", []):
                accounts[other["id"]] = {'name': other.get("name"),
                                         'type': "other_token",
                                         'access_token': other.get("access_token"),
                                         'id': other.get("id"),
                                         'expires': 0}

            accounts[id] = {'name': name,
                            'type': type_token,
                            'access_token': token,
                            'expires': date,
                            'id': id}

            registry['collective.facebook.accounts'] = accounts
            #self.status = _("Facebook account succesfully authorized.")

            logger.info("Everything ok. redirecting...")
            self.request.RESPONSE.redirect('@@facebook-controlpanel')

        return super(FacebookControlPanel, self).__call__()

    def getAccounts(self):
        registry = getUtility(IRegistry)
        accounts = registry.get('collective.facebook.accounts', None)

        return accounts


class RemoveAuthAccount(BrowserView):

    def __call__(self, account_name):
        registry = getUtility(IRegistry)
        accounts = registry.get('collective.facebook.accounts', None)
        if not accounts:
            accounts = {}

        try:
            del accounts[account_name]
            registry['collective.facebook.accounts'] = accounts
        except:
            pass
