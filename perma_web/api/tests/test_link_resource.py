import os
from .utils import ApiResourceTransactionTestCase, TEST_ASSETS_DIR
from api.resources import LinkResource
from perma.models import Link, LinkUser

from django.core.files.storage import default_storage


# Use a TransactionTestCase here because archive capture is threaded
class LinkResourceTestCase(ApiResourceTransactionTestCase):
    fixtures = ['fixtures/users.json',
                'fixtures/archive.json',
                'fixtures/api_keys.json']

    serve_files = [os.path.join(TEST_ASSETS_DIR, 'target_capture_files/test.html'),
                   os.path.join(TEST_ASSETS_DIR, 'target_capture_files/noarchive.html'),
                   os.path.join(TEST_ASSETS_DIR, 'target_capture_files/test.pdf')]

    def setUp(self):
        super(LinkResourceTestCase, self).setUp()

        self.user = LinkUser.objects.get(email='test_vesting_member@example.com')
        self.user_2 = LinkUser.objects.get(email='test_registrar_member@example.com')
        self.link_1 = Link.objects.get(pk='7CF8-SS4G')

        self.list_url = "{0}/{1}/".format(self.url_base, LinkResource.Meta.resource_name)
        self.detail_url = "{0}{1}/".format(self.list_url, self.link_1.pk)

        self.get_data = {
            'vested': False,
            'vested_timestamp': None,
            'notes': '',
            'title': 'arxiv.org',
            'created_by': {'first_name': 'Vesting', 'last_name': 'Member', 'id': 3, 'resource_uri': ''},
            'url': 'http://arxiv.org/pdf/1406.3611.pdf',
            'dark_archived_robots_txt_blocked': False,
            'dark_archived': False,
            'vested_by_editor': None,
            'guid': str(self.link_1.guid),
            'creation_timestamp': '2014-06-16T15:23:24',
            'vesting_org': None,
            'resource_uri': self.detail_url
        }

        self.post_data = {
            'url': self.server_url + "/test.html",
            'title': 'This is a test page'
        }

    def assertHasAsset(self, link, capture_type):
        """
            Make sure capture of given type was created on disk and stored with this asset.
        """
        asset = link.assets.first()
        self.assertTrue(
            default_storage.exists(os.path.join(asset.base_storage_path, getattr(asset, capture_type))),
            "Failed to create %s for %s." % (capture_type, link.submitted_url))

    def get_credentials(self, user=None):
        user = user or self.user
        return self.create_apikey(username=user.email, api_key=user.api_key.key)

    def test_get_list_json(self):
        resp = self.api_client.get(self.list_url, format='json')
        self.assertValidJSONResponse(resp)

        objs = self.deserialize(resp)['objects']
        self.assertEqual(len(objs), Link.objects.count())
        self.assertKeys(objs[0], self.get_data.keys())

    def test_get_detail_json(self):
        resp = self.api_client.get(self.detail_url, format='json')
        self.assertValidJSONResponse(resp)
        self.assertKeys(self.deserialize(resp), self.get_data.keys())

    def test_post_list_unauthenticated(self):
        self.assertHttpUnauthorized(
            self.api_client.post(self.list_url,
                                 format='json',
                                 data=self.post_data))

    ########################
    # URL Archive Creation #
    ########################

    def test_should_create_archive_from_html_url(self):
        count = Link.objects.count()
        self.assertHttpCreated(
            self.api_client.post(self.list_url,
                                 format='json',
                                 data={'url': self.server_url + "/test.html"},
                                 authentication=self.get_credentials()))

        self.assertEqual(Link.objects.count(), count+1)

        link = Link.objects.latest('creation_timestamp')
        self.assertHasAsset(link, "image_capture")
        self.assertHasAsset(link, "warc_capture")
        self.assertFalse(link.dark_archived_robots_txt_blocked)
        self.assertEqual(link.submitted_title, "Test title.")

    def test_should_create_archive_from_pdf_url(self):
        count = Link.objects.count()
        self.assertHttpCreated(
            self.api_client.post(self.list_url,
                                 format='json',
                                 data={'url': self.server_url + "/test.pdf"},
                                 authentication=self.get_credentials()))

        self.assertEqual(Link.objects.count(), count+1)

        link = Link.objects.latest('creation_timestamp')
        self.assertHasAsset(link, "pdf_capture")

    def test_should_add_http_to_url(self):
        count = Link.objects.count()
        self.assertHttpCreated(
            self.api_client.post(self.list_url,
                                 format='json',
                                 data={'url': self.server_url.split("//")[1] + "/test.html"},
                                 authentication=self.get_credentials()))

        self.assertEqual(Link.objects.count(), count+1)

    def test_should_dark_archive_when_noarchive_in_html(self):
        count = Link.objects.count()
        self.assertHttpCreated(
            self.api_client.post(self.list_url,
                                 format='json',
                                 data={'url': self.server_url + "/noarchive.html"},
                                 authentication=self.get_credentials()))

        self.assertEqual(Link.objects.count(), count+1)

        link = Link.objects.latest('creation_timestamp')
        self.assertTrue(link.dark_archived_robots_txt_blocked)

    def test_should_dark_archive_when_disallowed_in_robots_txt(self):
        count = Link.objects.count()

        with self.serve_file(os.path.join(TEST_ASSETS_DIR, 'target_capture_files/robots.txt')):
            self.assertHttpCreated(
                self.api_client.post(self.list_url,
                                     format='json',
                                     data={'url': self.server_url + "/test.html"},
                                     authentication=self.get_credentials()))

        self.assertEqual(Link.objects.count(), count+1)

        link = Link.objects.latest('creation_timestamp')
        self.assertTrue(link.dark_archived_robots_txt_blocked)

    #########################
    # File Archive Creation #
    #########################

    def test_should_create_archive_from_pdf_file(self):
        count = Link.objects.count()
        with open(os.path.join(TEST_ASSETS_DIR, 'target_capture_files', 'test.pdf')) as test_file:
            data = dict(self.post_data.copy(), file=test_file)
            self.assertHttpCreated(
                self.api_client.post(self.list_url,
                                     format='multipart',
                                     data=data,
                                     authentication=self.get_credentials()))

            self.assertEqual(Link.objects.count(), count+1)

            link = Link.objects.latest('creation_timestamp')
            self.assertHasAsset(link, "pdf_capture")

    def test_should_create_archive_from_jpg_file(self):
        count = Link.objects.count()
        with open(os.path.join(TEST_ASSETS_DIR, 'target_capture_files', 'test.jpg')) as test_file:
            data = dict(self.post_data.copy(), file=test_file)
            self.assertHttpCreated(
                self.api_client.post(self.list_url,
                                     format='multipart',
                                     data=data,
                                     authentication=self.get_credentials()))

            self.assertEqual(Link.objects.count(), count+1)

            link = Link.objects.latest('creation_timestamp')
            self.assertHasAsset(link, "image_capture")

    #########
    # Other #
    #########

    def test_patch_detail(self):
        # Grab the current data & modify it slightly.
        resp = self.api_client.get(self.detail_url, format='json')
        self.assertValidJSONResponse(resp)
        old_data = self.deserialize(resp)
        new_data = dict(old_data,
                        vested=True,
                        notes='These are test notes',
                        dark_archived=True)

        count = Link.objects.count()
        self.assertHttpAccepted(
            self.api_client.patch(self.detail_url,
                                  format='json',
                                  data=new_data,
                                  authentication=self.get_credentials()))

        # Make sure the count hasn't changed & we did an update.
        self.assertEqual(Link.objects.count(), count)

        link = Link.objects.get(pk=self.link_1.pk)
        for attr in ['dark_archived', 'vested', 'notes']:
            self.assertNotEqual(getattr(link, attr), old_data[attr])
            self.assertEqual(getattr(link, attr), new_data[attr])

    def test_delete_detail_unauthenticated(self):
        self.assertHttpUnauthorized(
            self.api_client.delete(self.detail_url,
                                   format='json'))

    def test_delete_detail(self):
        self.assertHttpOK(
            self.api_client.get(self.detail_url,
                                format='json'))

        self.assertHttpAccepted(
            self.api_client.delete(self.detail_url,
                                   format='json',
                                   authentication=self.get_credentials()))

        self.assertHttpNotFound(
            self.api_client.get(self.detail_url,
                                format='json'))
