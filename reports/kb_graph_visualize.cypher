// Use in Neo4j Browser, then take a screenshot.
:param user_id => 'user-0001';


// Query để vẽ graph "đẹp/phức tạp" trong Neo4j Browser (chạy rồi chụp ảnh)
// Mục tiêu: 1 user + hàng xóm (co-occurrence) + products + categories + queries
MATCH (me:User {id: $user_id})
OPTIONAL MATCH (me)-[:SEARCHED]->(q:Query)
WITH me, collect(DISTINCT q)[0..8] AS qs
OPTIONAL MATCH (me)-[r1]->(p:Product)<-[r2]-(other:User)-[r3]->(rec:Product)
WITH me, qs, p, other, rec, r1, r2, r3
LIMIT 200
OPTIONAL MATCH (p)-[:IN_CATEGORY]->(c1:Category)
OPTIONAL MATCH (rec)-[:IN_CATEGORY]->(c2:Category)
RETURN me, qs, p, other, rec, c1, c2, r1, r2, r3;

