# README

## What is this?

My class at CJS got access to a beta tool from enigma, and we wanted to use it to see how much the MCP could find to backround a company for an investigation.

To take it a step further, I added a few extra APIs to create the most robust possible free/opensource backrounding mcp. The main goal here
is to quickly and effectivly background a company for an investigation and identify easy starting leads or key related entities for me to begin looking into
and contacting human sources. Importantly, I also want this system to have the ability to link back to legit sources and export them as pdf when reqruied for
factcheking and due diligance. 

## Methodology

The GDLET and Open Sanctions MCPs are wrapped with locally running python serves to make it easiest for claude code to interact with through the MCP. 

The skill starts by trying to make sure it has identified the correct company or person. Next to runs a news search on GDELT over the past 3 months (because its free), then it tries to match an entites to "Company" or "Person" in the Open sanctions data API. From there it will run a websearch of EDGAR but it isn't super effective yet. From there it will hit Court Listner but only with the entity in qestion as a plaintiff or defendant. After all of that, it will hit the Engima MCP. I did this to try and understand how much prorietary data Enigma actually adds to a quick search, then it will synthesize and create an HTML with all of its findings presented with some helpful journalistic tools like a timeline, network graph, and key leads. 

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

## How has this been helpful to me?

This proccess, specifically for this investigation, surfaced concerns about federally regulated bond offerings that I am not famiiliar enough with to have thought to look for. Specifically a chronology problem with the SLP offerings that suggests some hidden money that isn't openly documented. 

This skill is also very good at finding early leads, but fails to supplant my own research or leads on a much more developed investigation. Best for a quick start, not a silver bullet. 
