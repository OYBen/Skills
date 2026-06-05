# v20260604 Schema Suppressed And EventService Bus Reclassified

Schema creation, migration, and init evidence is no longer emitted as business
endpoint inventory by default. Shuyun EventService runtime publish calls now
emit `EVENT_BUS_PUBLISHER` with `bus: eventservice`; schema kinds remain
suppressed from final output unless a future explicit schema-inventory mode is
added.

