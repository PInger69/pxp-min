# Avoca My Play-by-Play Python Server

This codebase contains the Python source code to support the My PxP Server.
The server essentially performs two functions:

1. It provides the web application that performs system admin functions; and
2. It provides the server's REST API that's used to manage tags, thumbnails,
and video.

## Execution Context

The server code is executed using an Apache httpd server, using CGI. Here are some
notes about that configuration:

* The httpd.conf requires a few options to be set:
  * The document root should be `/var/www/html`. There are hard-coded references to this 
    directory in the Python code
  * The directory configuration should include `Options FollowSymLinks Multiviews ExecCGI` 
    and `AllowOverride All`. The latter allows the `.htaccess` file to apply some 
    rewrite rules.
  * Add `index.py` to the `DirectoryIndex` like so: `DirectoryIndex index.html index.py`
  * Ensure the the CGI module is loaded: `LoadModule cgi_module libexec/apache2/mod_cgi.so`
  * Ensure that there's a `.py` option in the CGI Handlers: `AddHandler cgi-script .cgi .py`
* The Python could should be checked out in to the `/var/www/html/min` directory.
* The Python environment needs some extra stuff to be added to it. Loading that extra
  stuff in newer versions of macOS is tricky, because the System Integrity Protection 
  (SIP) really doesn't want you changing the standard Apple-delivered Python 
  installation in the OS Library. You really have two options here:
  * deactivate SIP and install the modules
  * install another version of Python and install the modules, there.
* Some of the necessary modules include `pybonjour`, `psutil`, `dicttoxml`, `netifaces`, 
  and `wheezy.template`
* Some pre-existing files and directories are necessary, including the 
  `/var/www/html/events/_db` and `/var/www/html/events/session`

## Oddities

1. The REST API doesn't take in JSON using the standard mechanism. It, instead,
passes the incoming JSON as a URL-encoded path element, like so:

```
http://172.18.2.188/min/ajax/gametags/%7B%22device%22%3A%227C79C4F5-07AD-4553-82C7-D77240993A7E%22,%22requesttime%22%3A123203.903092528,%22event%22%3A%222017-03-30_17-31-21_5340deac70bf95beaf90737a8fe900da0ed03f24_local%22,%22user%22%3A%22356a192b7913b04c54574d18c28d46e6395428ab%22%7D
```

2. The REST responses don't correctly describe the returned content-type.
Instead, the responses claim to be "text/html", rather than "application/json".
