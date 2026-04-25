// Use in Neo4j Browser, then take a screenshot.
// Tip: After RUN, open the result "Graph" view (not the Guide panel).

// 0) (Optional) Pick a user id. If this user has few edges, use the "top users" query below.
:param user_id => 'user-0001';

// 1) Sanity check: does the user exist?
MATCH (u:User {id: $user_id})
RETURN u
LIMIT 1;

// 2) If graph is small/empty for this user, find users with the most relationships (choose one id, set :param user_id).
MATCH (u:User)-[r]->()
RETURN u.id AS user_id, count(r) AS degree
ORDER BY degree DESC
LIMIT 10;

// 3) Graph visualization query (returns nodes + relationships directly so Neo4j Browser renders the graph).
// Goal: 1 user + searched queries + interacted products + neighbor users + recommended products + categories
MATCH (me:User {id: $user_id})
OPTIONAL MATCH (me)-[sr:SEARCHED]->(q:Query)
WITH me, sr, q
OPTIONAL MATCH (me)-[r1]->(p:Product)
OPTIONAL MATCH (p)-[:IN_CATEGORY]->(c1:Category)
WITH me, sr, q, r1, p, c1
OPTIONAL MATCH (me)-[r2]->(p2:Product)<-[r3]-(other:User)-[r4]->(rec:Product)
OPTIONAL MATCH (rec)-[:IN_CATEGORY]->(c2:Category)
RETURN me, sr, q, r1, p, c1, other, r3, r4, rec, c2
LIMIT 400;

