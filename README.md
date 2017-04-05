# Avoca My Play-by-Play Python Server

This codebase contains the Python source code to support the My PxP Server.
The server essentially performs two functions:

1. It provides the web application that performs system admin functions; and
2. It provides the server's REST API that's used to manage tags, thumbnails,
and video.

## Oddities

1. The REST API doesn't take in JSON using the standard mechanism. It, instead,
passes the incoming JSON as a URL-encoded path element, like so:

{code}
http://172.18.2.188/min/ajax/gametags/%7B%22device%22%3A%227C79C4F5-07AD-4553-82C7-D77240993A7E%22,%22requesttime%22%3A123203.903092528,%22event%22%3A%222017-03-30_17-31-21_5340deac70bf95beaf90737a8fe900da0ed03f24_local%22,%22user%22%3A%22356a192b7913b04c54574d18c28d46e6395428ab%22%7D
{code}

2. The REST responses don't correctly describe the returned content-type.
Instead, the responses claim to be "text/html", rather than "application/json".
