import os, sys, subprocess, urllib, glob, shutil
from celery import task
from django.conf import settings

from linky_web.linky.models import Asset
from linky_web.linky.exceptions import BrokenURLError

@task
def get_screen_cap(link_guid, target_url, base_storage_path):
    """ Create an image from the url, store it in a dir. use the id as part of the dir path """

    path_elements = [settings.GENERATED_ASSETS_STORAGE, base_storage_path, 'cap.png']

    if not os.path.exists(os.path.sep.join(path_elements[:2])):
        os.makedirs(os.path.sep.join(path_elements[:2]))

    image_generation_command = settings.PROJECT_ROOT + '/lib/phantomjs ' + settings.PROJECT_ROOT + '/lib/rasterize.js "' + target_url + '" ' + os.path.sep.join(path_elements)
    
    subprocess.call(image_generation_command, shell=True)

    if not os.path.exists(os.path.sep.join(path_elements)):
        return False

    asset = Asset.objects.get(link__guid=link_guid)
    asset.image_capture = os.path.sep.join(path_elements[2:])
    asset.save()
    
    return True
    
@task
def get_source(link_guid, target_url, base_storage_path, user_agent=''):

    path_elements = [settings.GENERATED_ASSETS_STORAGE, base_storage_path, 'source', 'index.html']

    directory = os.path.sep.join(path_elements[:3])

    headers = {
        #'Accept': ','.join(settings.ACCEPT_CONTENT_TYPES),
        #'User-Agent': user_agent,
    }

    """ Get the markup and assets, update our db, and write them to disk """
    # Construct wget command
    command = 'wget '
    command = command + '--quiet ' # turn off wget's output
    command = command + '--tries=' + str(settings.NUMBER_RETRIES) + ' ' # number of retries (assuming no 404 or the like)
    command = command + '--wait=' + str(settings.WAIT_BETWEEN_TRIES) + ' ' # number of seconds between requests (lighten the load on a page that has a lot of assets)
    command = command + '--quota=' + settings.ARCHIVE_QUOTA + ' ' # only store this amount
    command = command + '--random-wait ' # random wait between .5 seconds and --wait=
    command = command + '--limit-rate=' + settings.ARCHIVE_LIMIT_RATE  + ' ' # we'll be performing multiple archives at once. let's not download too much in one stream
    command = command + '--adjust-extension '  # if a page is served up at .asp, adjust to .html. (this is the new --html-extension flag)
    command = command + '--span-hosts ' # sometimes things like images are hosted at a CDN. let's span-hosts to get those
    command = command + '--convert-links ' # rewrite links in downloaded source so they can be viewed in our local version
    command = command + '-e robots=off ' # we're not crawling, just viewing the page exactly as you would in a web-browser.
    command = command + '--page-requisites ' # get the things required to render the page later. things like images.
    command = command + '--no-directories ' # when downloading, flatten the source. we don't need a bunch of dirs.
    command = command + '--user-agent="' + user_agent + '" ' # pass through our user's user agent
    command = command + '--directory-prefix=' + directory + ' ' # store our downloaded source in this directory
    
    # Add headers (defined earlier in this function)
    for key, value in headers.iteritems():
        command = command + '--header="' + key + ': ' + value+ '" '
    command = command + target_url # Download the user-specified URL

    # Download page data and dependencies
    if not os.path.exists(directory):
        os.makedirs(directory)
    
    #TODO replace os.popen with subprocess
    output = os.popen(command)

    # Verify success
    if '400 Bad Request' in output:
        asset = Asset.objects.get(link__guid=link_guid)
        asset.warc_capture = 'failed'
        asset.save()
        raise BrokenURLError(target_url)
        
    filename = urllib.unquote(target_url.split('/')[-1]).decode('utf8')
    if filename != '' and 'index.html' not in os.listdir(directory):
        try:
            src = os.path.join(directory, filename)
            des = os.path.sep.join(path_elements)
            shutil.move(src, des)
        except:
            # Rename the file as index.html if it contains '<html'
            counter = 0
            for filename in glob.glob(directory + '/*'):
                with open(filename) as f:
                    if '<html' in f.read():
                        shutil.move(os.path.join(directory, filename), os.path.sep.join(path_elements))
                        counter = counter + 1
            if counter == 0:
                # If we still don't have an index.html file, raise an exception and record it to the DB
                asset = Asset.objects.get(link__guid=link_guid)
                asset.warc_capture = 'failed'
                asset.save()
                
                os.system('rm -rf ' + directory)
                
                # Raise error if no HTML pages were retrieved
                raise BrokenURLError(target_url)
    
    if os.path.exists(os.path.sep.join(path_elements)):
        asset = Asset.objects.get(link__guid=link_guid)
        asset.warc_capture = os.path.sep.join(path_elements[2:])
        asset.save()