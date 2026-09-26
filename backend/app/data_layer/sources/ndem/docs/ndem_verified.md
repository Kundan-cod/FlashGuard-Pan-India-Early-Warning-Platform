# Verified NDEM facts

NRSC describes NDEM as a national repository of GIS-based data for the entire country with multi-scale databases and DSS tools, executed in collaboration with MHA for near-real-time disaster/emergency management. citeturn0search0

NRSC's current Disaster Management Support pages list NDEM alongside near-real-time flood monitoring, flood early warning, flood vulnerability, landslide hazard inventory and landslide early warning services. citeturn0search1turn0search3

Access limitation:
NDEM V4 documentation states the portal is protected and requires username/password obtained through an authorization form; authorized Central, State, District, NDRF and SDRF officials are listed as users. citeturn0search17

Older NDEM access documentation likewise states that non-base layers require login and that state-authorized officials receive state-specific access. citeturn0search16

Engineering decision:
- MVP: do not depend on NDEM credentials.
- Use public NRSC/Bhuvan products and our verified collectors for core prediction.
- NDEM becomes a high-value enrichment/response connector when official access is available.
- Never bypass authentication or invent an undocumented API.
- Store access_level and source-health separately from risk score.
