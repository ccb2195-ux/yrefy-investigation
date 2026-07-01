# README

## What is this?

My class at CJS got access to a beta tool from enigma, and we wanted to use it to see how much the MCP could find to backround a company for an investigation.

To take it a step further, I added a few extra APIs to create the most robust possible free/opensource backrounding mcp. The main goal here
is to quickly and effectivly background a company for an investigation and identify easy starting leads or key related entities for me to begin looking into
and contacting human sources. Importantly, I also want this system to have the ability to link back to legit sources and export them as pdf when reqruied for
factcheking and due diligance. 

## Methodology

(1) GDELT -> Added this to get the best possible recent news analysis using a local server. 
(2) Open Sanctions -> Got a trial API Key with 50 calls/month to find entities on sanctions lists or who are otherwise politcially exposed.
(3) CourtListner -> Added free API to help scan as wide as possible for litigation against related entitites. 

## Where should this go next? 

I'd like to add the following connectors as well and make sure the fuzzy matchign for entity resolution is working:

(a) SEC EDGAR API
(b) Internet archive API
(c) GLEIF LEI API
(d) USAspending.gov API
(e) Propobulica nonprofit explorer API
