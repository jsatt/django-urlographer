# Copyright 2013 Consumers Unified LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from django.contrib.sites.models import Site
from django.contrib.admin.sites import AdminSite
from django.core.urlresolvers import ResolverMatch
from django.http import Http404
from django.test import TestCase
from django.test.client import RequestFactory
import mox

from urlographer import models, utils, views


class URLMapTest(TestCase):
    def setUp(self):
        self.site = Site(domain='example.com')
        self.url = models.URLMap(site=self.site, path='/test_path')
        self.hexdigest = '389661d2e64f9d426ad306abe6e8f957'
        self.cache_key = models.CACHE_PREFIX + self.hexdigest
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_protocol(self):
        self.assertEqual(self.url.protocol(), 'http')

    def test_https_protocol(self):
        self.url.force_secure = True
        self.assertEqual(self.url.protocol(), 'https')

    def test_unicode(self):
        self.assertEqual(unicode(self.url), u'http://example.com/test_path')

    def test_https_unicode(self):
        self.url.force_secure = True
        self.assertEqual(unicode(self.url), u'https://example.com/test_path')

    def test_set_hexdigest(self):
        self.assertFalse(self.url.hexdigest)
        self.url.set_hexdigest()
        self.assertEqual(
            self.url.hexdigest, self.hexdigest)

    def test_save(self):
        self.site.save()
        self.url.site = self.site
        self.url.status_code = 204
        self.assertFalse(self.url.id)
        self.assertFalse(self.url.hexdigest)
        self.mox.StubOutWithMock(models.cache, 'set')
        models.cache.set(
            self.cache_key, self.url, timeout=models.CACHE_TIMEOUT)
        self.mox.ReplayAll()
        self.url.save()
        self.mox.VerifyAll()
        self.assertEqual(self.url.hexdigest, self.hexdigest)
        self.assertEqual(self.url.id, 1)

    def test_save_invalid_redirect_raises(self):
        self.site.save()
        self.url.site = self.site
        self.url.status_code = 301
        self.assertRaises(AssertionError, self.url.save)
        self.url.status_code = 302
        self.assertRaises(AssertionError, self.url.save)
        self.url.redirect = self.url
        self.assertRaises(AssertionError, self.url.save)
        self.url.status_code = 200
        self.url.redirect = models.URLMap.objects.create(
            site=self.site, path='/target', status_code=204)
        self.assertRaises(AssertionError, self.url.save)

    def test_cached_get_cache_hit(self):
        self.mox.StubOutWithMock(models.cache, 'get')
        models.cache.get(self.cache_key).AndReturn(self.url)
        self.mox.ReplayAll()
        url = models.URLMap.objects.cached_get(self.site, self.url.path)
        self.mox.VerifyAll()
        self.assertEqual(url, self.url)

    def test_cached_get_cache_miss(self):
        self.site.save()
        self.url.site = self.site
        self.url.status_code = 204
        self.url.save()
        self.mox.StubOutWithMock(models.cache, 'get')
        self.mox.StubOutWithMock(models.cache, 'set')
        models.cache.get(self.cache_key)
        models.cache.set(
            self.cache_key, self.url, timeout=models.CACHE_TIMEOUT)
        self.mox.ReplayAll()
        url = models.URLMap.objects.cached_get(self.site, self.url.path)
        self.mox.VerifyAll()
        self.assertEqual(url, self.url)

    def test_cached_get_does_not_exist(self):
        self.mox.StubOutWithMock(models.cache, 'get')
        models.cache.get(self.cache_key)
        self.mox.ReplayAll()
        self.assertRaises(
            models.URLMap.DoesNotExist, models.URLMap.objects.cached_get, self.site,
            self.url.path)
        self.mox.VerifyAll()


class ContentMapTest(TestCase):
    def test_save_nonexistent_view(self):
        content_map = models.ContentMap(view='urlographer.views.nonexistent')
        self.assertRaises(AttributeError, content_map.save)

    def test_save(self):
        # infinite recursion FTW
        content_map = models.ContentMap(view='urlographer.views.route')
        content_map.save()
        self.assertEqual(content_map.id, 1)


class RouteTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.site = Site.objects.create(domain='example.com')
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_route_not_found(self):
        request = self.factory.get('/404')
        self.assertEqual(request.path, '/404')
        self.assertRaises(Http404, views.route, request)

    def test_route_gone(self):
        models.URLMap.objects.create(
            site=self.site, status_code=410, path='/410')
        request = self.factory.get('/410')
        response = views.route(request)
        self.assertEqual(response.status_code, 410)

    def test_route_redirect_canonical(self):
        content_map = models.ContentMap(
            view='django.views.generic.base.TemplateView')
        content_map.options['initkwargs'] = {
            'template_name': 'admin/base.html'}
        content_map.save()
        models.URLMap.objects.create(site=self.site, path='/test',
                                  content_map=content_map)
        response = views.route(self.factory.get('/TEST'))
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response._headers['location'][1],
                         'http://example.com/test')

    def test_permanent_redirect(self):
        target = models.URLMap.objects.create(
            site=self.site, path='/target', status_code=204)
        models.URLMap.objects.create(
            site=self.site, path='/source', redirect=target, status_code=301)
        response = views.route(self.factory.get('/source'))
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response._headers['location'][1],
                         'http://example.com/target')

    def test_redirect(self):
        target = models.URLMap.objects.create(
            site=self.site, path='/target', status_code=204)
        models.URLMap.objects.create(
            site=self.site, path='/source', redirect=target, status_code=302)
        response = views.route(self.factory.get('/source'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response._headers['location'][1],
                         'http://example.com/target')

    def test_content_map_class_based_view(self):
        content_map = models.ContentMap(
            view='django.views.generic.base.TemplateView')
        content_map.options['initkwargs'] = {
            'template_name': 'admin/base.html'}
        content_map.save()
        models.URLMap.objects.create(
            site=self.site, path='/test', content_map=content_map)
        response = views.route(self.factory.get('/test'))
        self.assertEqual(response.status_code, 200)

    def test_content_map_view_function(self):
        content_map = models.ContentMap(
            view='django.views.generic.simple.direct_to_template')
        content_map.options['template'] = 'admin/base.html'
        content_map.save()
        models.URLMap.objects.create(
            site=self.site, path='/test', content_map=content_map)
        response = views.route(self.factory.get('/test'))
        self.assertEqual(response.status_code, 200)

# the test below only works if .* is mapped to route
#    def test_route_trailing_slash_redirect(self):
#        self.mox.StubOutWithMock(views, 'resolve')
#        views.resolve('/admin/').AndReturn(
#            ResolverMatch(AdminSite().index, (), {}, 'index'))
#        self.mox.ReplayAll()
#        response = views.route(self.factory.get('/admin'))
#        self.mox.VerifyAll()
#        self.assertEqual(response.status_code, 301)
#        self.assertEqual(response._headers['location'][1], '/admin/')



class CanonicalizePathTest(TestCase):
    def test_lower(self):
        self.assertEqual(utils.canonicalize_path('/TEST'), '/test')

    def test_slashes(self):
        self.assertEqual(utils.canonicalize_path('//t//e///s/t'),
                         '/t/e/s/t')

    def test_dots(self):
        self.assertEqual(
            utils.canonicalize_path('./../this/./is/./only/../a/./test.html'),
            '/this/is/a/test.html')
        self.assertEqual(
            utils.canonicalize_path('../this/./is/./only/../a/./test.html'),

            '/this/is/a/test.html')

    def test_non_ascii(self):
        self.assertEqual(utils.canonicalize_path(u'/te\xa0\u2013st'), '/test')