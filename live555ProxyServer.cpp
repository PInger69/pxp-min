/**********
This library is free software; you can redistribute it and/or modify it under
the terms of the GNU Lesser General Public License as published by the
Free Software Foundation; either version 2.1 of the License, or (at your
option) any later version. (See <http://www.gnu.org/copyleft/lesser.html>.)

This library is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for
more details.

You should have received a copy of the GNU Lesser General Public License
along with this library; if not, write to the Free Software Foundation, Inc.,
51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
**********/
// Copyright (c) 1996-2014, Live Networks, Inc.  All rights reserved
// LIVE555 Proxy Server
// main program
//////////////////////////////////////////////////////////////
////                                                      ////
////           copy this file to live/proxyServer         ////
////             then run ./genMakefiles linux            ////
////               or ./genMakefiles macosx               ////
////               from the live/ directory               ////
////                    then run make                     ////
////                                                      ////
//////////////////////////////////////////////////////////////
#include "liveMedia.hh"
#include "BasicUsageEnvironment.hh"
// #include <stdlib.h>
// #include <stdio.h>
char const* progName;
UsageEnvironment* env;
UserAuthenticationDatabase* authDB = NULL;
UserAuthenticationDatabase* authDBForREGISTER = NULL;

// Default values of command-line parameters:
int verbosityLevel = 0;
Boolean streamRTPOverTCP = False;
portNumBits tunnelOverHTTPPortNum = 0;
char* username = NULL;
char* password = NULL;
Boolean proxyREGISTERRequests = False;
char* usernameForREGISTER = NULL;
char* passwordForREGISTER = NULL;
char* urlFilePath = NULL;

static RTSPServer* createRTSPServer(Port port) {
  if (proxyREGISTERRequests) {
    return RTSPServerWithREGISTERProxying::createNew(*env, port, authDB, authDBForREGISTER, 65, streamRTPOverTCP, verbosityLevel);
  } else {
    return RTSPServer::createNew(*env, port, authDB);
  }
}

void usage(int code) {
  *env << "Usage: " << progName << " [options] -o <filename> <rtsp-url-1> ... <rtsp-url-n>\n"
      << " <filename> file path where the url of the proxy server will be stored\n"
      << " <rtsp-url-n> - url of the RTSP server to proxy. multiple proxies can be specified\n"
      << "Options: \n"
      << " [-p <port>] - try to set up proxy on this port. if unsuccessful, will try next available port (+1)\n"
      << " [-R] - Handle incoming REGISTER requests by proxying the specified stream\n"
      << " [-t] - stream over TCP connection\n"
      << " [-u <username> <password>] - username and password for backend server authentication\n"
      << " [-U <username-for-REGISTER> <password-for-REGISTER>] - username and password that clients connecting to this server have to specify\n"
      << " [-v|-V] - v: verbose output, V: more verbose output\n";
       
  exit(1);
}

int main(int argc, char** argv) {
  // Increase the maximum size of video frames that we can 'proxy' without truncation.
  // (Such frames are unreasonably large; the back-end servers should really not be sending frames this large!)
  OutPacketBuffer::maxSize = 180000; // bytes

  portNumBits startRTPPort = 8554; //try to set up proxy on this port first (can be overridden by user)

  // Begin by setting up our usage environment:
  TaskScheduler* scheduler = BasicTaskScheduler::createNew();
  env = BasicUsageEnvironment::createNew(*scheduler);

  *env << "LIVE555 Proxy Server v 1.0\n"
       << "\t(LIVE555 Streaming Media library version "
       << LIVEMEDIA_LIBRARY_VERSION_STRING << ")\n\n";
  // Check command-line arguments: optional parameters, then one or more rtsp:// URLs (of streams to be proxied):
  progName = argv[0];
  if (argc < 2) usage(1);
  while (argc > 1) {
    // Process initial command-line options (beginning with "-"):
    char* const opt = argv[1];
    if (opt[0] != '-') break; // the remaining parameters are assumed to be "rtsp://" URLs

    switch (opt[1]) {
    case 'o': { // output the url to the specified file
      if (argc > 3 && argv[2][0] != '-') {
         // The next argument is the file name:
          urlFilePath = argv[2];
          ++argv; --argc;
          break;
        }
      usage(2); //the file path was not specified
      break;
    }
    case 'p':{
      if(argc<3){
        usage(3);
      }
      startRTPPort = atoi(argv[2]);
      argv++; argc--;
      break;
    }

    case 'v': { // verbose output
      verbosityLevel = 1;
      break;
    }

    case 'V': { // more verbose output
      verbosityLevel = 2;
      break;
    }

    case 't': {
      // Stream RTP and RTCP over the TCP 'control' connection.
      // (This is for the 'back end' (i.e., proxied) stream only.)
      streamRTPOverTCP = True;
      break;
    }

    // case 'T': {
    //   // stream RTP and RTCP over a HTTP connection
    //   if (argc > 3 && argv[2][0] != '-') {
    //      // The next argument is the HTTP server port number:                                                                       
    //     if (sscanf(argv[2], "%hu", &tunnelOverHTTPPortNum) == 1
    //         && tunnelOverHTTPPortNum > 0) {
    //       ++argv; --argc;
    //       break;
    //     }
    //   }

    //   // If we get here, the option was specified incorrectly:
    //   usage(4);
    //   break;
    // }

    case 'u': { // specify a username and password (to be used if the 'back end' (i.e., proxied) stream requires authentication)
      if (argc < 4) usage(5); // there's no argv[3] (for the "password")
      username = argv[2];
      password = argv[3];
      argv += 2; argc -= 2;
      break;
    }

    case 'U': { // specify a username and password to use to authenticate incoming "REGISTER" commands
      if (argc < 4) usage(6); // there's no argv[3] (for the "password")
      usernameForREGISTER = argv[2];
      passwordForREGISTER = argv[3];

      if (authDBForREGISTER == NULL) authDBForREGISTER = new UserAuthenticationDatabase;
      authDBForREGISTER->addUserRecord(usernameForREGISTER, passwordForREGISTER);
      argv += 2; argc -= 2;
      break;
    }

    case 'R': { // Handle incoming "REGISTER" requests by proxying the specified stream:
      proxyREGISTERRequests = True;
      break;
    }

    default: {
      usage(7);
      break;
    }
    }

    ++argv; --argc;
  }
  if (argc < 2 && !proxyREGISTERRequests) usage(8); // there must be at least one "rtsp://" URL at the end 
  // Make sure that the remaining arguments appear to be "rtsp://" URLs:
  int i;
  for (i = 1; i < argc; ++i) {
    if (strncmp(argv[i], "rtsp://", 7) != 0) usage(9);
  }
  // Do some additional checking for invalid command-line argument combinations:
  if (authDBForREGISTER != NULL && !proxyREGISTERRequests) {
    *env << "The '-U <username> <password>' option can be used only with -R\n";
    usage(10);
  }
  if (streamRTPOverTCP) {
    if (tunnelOverHTTPPortNum > 0) {
      *env << "The -t and -T options cannot both be used!\n";
      usage(11);
    } else {
      tunnelOverHTTPPortNum = (portNumBits)(~0); // hack to tell "ProxyServerMediaSession" to stream over TCP, but not using HTTP
    }
  }

#ifdef ACCESS_CONTROL
  // To implement client access control to the RTSP server, do the following:
  authDB = new UserAuthenticationDatabase;
  authDB->addUserRecord("username1", "password1"); // replace these with real strings
      // Repeat this line with each <username>, <password> that you wish to allow access to the server.
#endif

  // Create the RTSP server.  Try first with the 8554 port, if failed, try all subsequent ports:
  RTSPServer* rtspServer;
  portNumBits rtspServerPortNum = startRTPPort;
  rtspServer = createRTSPServer(rtspServerPortNum);
  while(rtspServer == NULL && rtspServerPortNum<20000) {
    rtspServerPortNum++;
    rtspServer = createRTSPServer(rtspServerPortNum);
  }
  if (rtspServer == NULL) {
    *env << "Failed to create RTSP server: " << env->getResultMsg() << "\n";
    exit(1);
  }

  // Create a proxy for each "rtsp://" URL specified on the command line:
  for (i = 1; i < argc; ++i) {
    char const* proxiedStreamURL = argv[i];
    char streamName[30];
    if (argc == 2) {
      sprintf(streamName, "%s", "pxpstr"); // there's just one stream; give it this name
    } else {
      sprintf(streamName, "pxpstr-%d", i); // there's more than one stream; distinguish them by name
    }
    ServerMediaSession* sms
      = ProxyServerMediaSession::createNew(*env, rtspServer,
             proxiedStreamURL, streamName,
             username, password, tunnelOverHTTPPortNum, verbosityLevel);
    rtspServer->addServerMediaSession(sms);

    char* proxyStreamURL = rtspServer->rtspURL(sms);
    // output the url to a file
    char outCmd[255] = "";
    if(urlFilePath){
      sprintf(outCmd,"echo \"%s\" > %s",proxyStreamURL,urlFilePath);
      system(outCmd);      
    }
    *env << "RTSP stream, proxying the stream \"" << proxiedStreamURL << "\"\n";
    *env << "\tPlay this stream using the URL: " << proxyStreamURL << "\n";
    delete[] proxyStreamURL;
  }

  if (proxyREGISTERRequests) {
    *env << "(We handle incoming \"REGISTER\" requests on port " << rtspServerPortNum << ")\n";
  }

  // Also, attempt to create a HTTP server for RTSP-over-HTTP tunneling.
  // Try first with the default HTTP port (80), and then with the alternative HTTP
  // port numbers (8000 and 8080).
  // for the purposes of this app, there is not going to be any tunnelling
  // if (rtspServer->setUpTunnelingOverHTTP(80) || rtspServer->setUpTunnelingOverHTTP(8000) || rtspServer->setUpTunnelingOverHTTP(8080)) {
  //   *env << "\n(We use port " << rtspServer->httpServerPortNum() << " for optional RTSP-over-HTTP tunneling.)\n";
  // } else {
    *env << "\n(RTSP-over-HTTP tunneling is not available.)\n";
  // }

  // Now, enter the event loop:
  env->taskScheduler().doEventLoop(); // does not return

  return 0; // only to prevent compiler warning
}
