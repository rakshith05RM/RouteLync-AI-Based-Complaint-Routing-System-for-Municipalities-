# Diagrams for the project report

Diagrams that must match the code are **generated from it**: run `python manage.py export_diagrams` to refresh
`er_diagram.mmd` (all 23 tables and relationships) and `lifecycle.mmd` (every allowed status change).
Mermaid diagrams render in VS Code (Markdown preview with a Mermaid extension), GitHub, or https://mermaid.live.
PlantUML diagrams render at https://www.plantuml.com/plantuml or in the VS Code PlantUML extension.

## 1. Use case diagram (PlantUML)
```plantuml
@startuml
left to right direction
actor Citizen
actor "Department Officer" as Officer
actor "Field Worker" as Worker
actor Administrator as Admin
rectangle RouteLync {
  usecase "Register / sign in / reset password" as UC1
  usecase "Submit complaint (location, GPS, photo)" as UC2
  usecase "Track complaint and receive notifications" as UC3
  usecase "Confirm fix, reopen, give feedback" as UC4
  usecase "View department queue (filters, drill-down, map)" as UC5
  usecase "Assign / reassign field worker" as UC6
  usecase "Verify resolution, reject, change priority" as UC7
  usecase "Escalate complaint" as UC8
  usecase "Review possible duplicates" as UC9
  usecase "Start and complete assigned work" as UC10
  usecase "Verify or correct AI routing" as UC11
  usecase "Train, review and activate AI model" as UC12
  usecase "Manage users, departments, SLA" as UC13
  usecase "View analytics and audit log" as UC14
  usecase "Classify and route complaint (NLP + Naive Bayes)" as UC15
  usecase "Monitor SLA and escalate automatically" as UC16
}
Citizen --> UC1
Citizen --> UC2
Citizen --> UC3
Citizen --> UC4
Officer --> UC5
Officer --> UC6
Officer --> UC7
Officer --> UC8
Officer --> UC9
Worker --> UC10
Admin --> UC11
Admin --> UC12
Admin --> UC13
Admin --> UC14
Admin --> UC9
UC2 ..> UC15 : <<include>>
UC16 ..> UC8 : <<include>>
@enduml
```

## 2. Data flow diagram, level 0 (Mermaid)
```mermaid
flowchart LR
  C([Citizen]) -- complaint, feedback --> S((RouteLync))
  S -- status, notifications --> C
  O([Department Officer]) -- assignments, verification --> S
  S -- department queue, map --> O
  W([Field Worker]) -- progress, completion --> S
  S -- assigned jobs --> W
  A([Administrator]) -- corrections, settings, training --> S
  S -- analytics, audit log --> A
```

## 3. Data flow diagram, level 1 (Mermaid)
```mermaid
flowchart TB
  C([Citizen]) -->|credentials| P1((1 Authenticate))
  P1 <--> D1[(D1 Users)]
  C -->|complaint + location + photo| P2((2 Validate and store))
  P2 --> D2[(D2 Complaints)]
  P2 --> P3((3 Classify and route))
  D3[(D3 Training data and models)] --> P3
  P3 -->|department, confidence, priority, SLA| D2
  P3 -->|low confidence| P7((7 Administer and verify))
  O([Officer]) --> P4((4 Manage workflow))
  W([Worker]) --> P4
  D2 <--> P4
  P4 --> P6((6 Notify))
  P5((5 Monitor SLA and escalate)) --> D2
  P5 --> P6
  P6 --> D5[(D5 Notifications)]
  A([Administrator]) --> P7
  P7 --> D2
  P7 -->|verified examples| D3
  P7 --> D4[(D4 Audit log)]
  P4 --> D4
  D5 --> C
```

## 4. Class diagram (PlantUML, main classes)
```plantuml
@startuml
class User { email; full_name; phone; role; is_active }
class CitizenProfile { address }
class OfficerProfile { designation; is_department_head }
class FieldWorkerProfile { employee_code; is_available }
class Department { name; code; is_active }
class Area { name }
class Ward { number }
class Complaint { title; description; status; priority; ai_confidence; routing_method; sla_deadline; escalation_level }
class ComplaintLocation { street; landmark; address_text; latitude; longitude }
class ComplaintImage { image; kind }
class ComplaintStatusHistory { from_status; to_status; note; timestamp }
class ComplaintAssignment { assigned_at; ended_at }
class ComplaintRemark { text; visibility }
class Resolution { remarks; outcome }
class Feedback { rating; comment }
class EscalationEvent { level; reason; automatic }
class DuplicateFlag { similarity; status }
class RoutingCorrection { ai_was_correct; was_unrouted }
class TrainingSample { text; is_verified; source }
class MLModel { version; accuracy; conf_threshold; is_active }
class Notification { message; is_read }
class AuditLog { action; summary; timestamp }
User "1" -- "0..1" CitizenProfile
User "1" -- "0..1" OfficerProfile
User "1" -- "0..1" FieldWorkerProfile
Department "1" -- "*" OfficerProfile
Department "1" -- "*" FieldWorkerProfile
Area "1" -- "*" Ward
Ward "1" -- "*" ComplaintLocation
User "1" -- "*" Complaint : citizen
Department "0..1" -- "*" Complaint
Complaint "1" -- "1" ComplaintLocation
Complaint "1" -- "*" ComplaintImage
Complaint "1" -- "*" ComplaintStatusHistory
Complaint "1" -- "*" ComplaintAssignment
Complaint "1" -- "*" ComplaintRemark
Complaint "1" -- "*" Resolution
Complaint "1" -- "0..1" Feedback
Complaint "1" -- "*" EscalationEvent
Complaint "1" -- "*" DuplicateFlag
Complaint "1" -- "*" RoutingCorrection
MLModel "0..1" -- "*" Complaint : used for prediction
Department "1" -- "*" TrainingSample
User "1" -- "*" Notification
@enduml
```

## 5. Sequence diagram: submission and routing (PlantUML)
```plantuml
@startuml
actor Citizen
participant "Django view" as V
participant "submit_complaint" as S
participant "route_complaint" as R
participant "ml_engine.predict" as M
database MySQL
Citizen -> V : POST form (text, ward, GPS, photo)
V -> V : validate text, ward/area, GPS range, image content
V -> S : save
S -> MySQL : complaint + location + history + image (one transaction)
V -> R : route
R -> M : predict(title + description)
M --> R : probabilities, confidence, influential terms
R -> R : rule-based priority and SLA deadline
alt confidence >= threshold and department active
  R -> MySQL : department, status PENDING, history
  R --> Citizen : notification "sent to the X department"
else low confidence, unknown words or model unavailable
  R -> MySQL : status NEEDS_VERIFICATION
  R --> Citizen : notification "being reviewed"
end
R -> R : flag possible duplicates
V --> Citizen : redirect to complaint page
@enduml
```

## 6. Sequence diagram: resolution (PlantUML)
```plantuml
@startuml
actor Officer
actor Worker
actor Citizen
participant RouteLync
Officer -> RouteLync : assign worker
RouteLync --> Worker : notification
Worker -> RouteLync : start work
RouteLync --> Citizen : "work has started"
Worker -> RouteLync : complete (remarks + REQUIRED photo of the fix)
RouteLync --> Officer : "waiting for verification"
Officer -> RouteLync : approve (or send back)
RouteLync --> Citizen : "resolved, please confirm" (proof photo shown)
alt problem fixed
  Citizen -> RouteLync : confirm, then feedback
else not fixed (within 7 days)
  Citizen -> RouteLync : reopen with reason
  RouteLync --> Officer : "reopened"
end
@enduml
```

## 7. Complaint lifecycle (Mermaid, generated)
Copy the contents of `docs/lifecycle.mmd`. Escalation is not a status: it is recorded as events and a level so work can continue.

## 8. Entity-relationship diagram (Mermaid, generated)
Copy the contents of `docs/er_diagram.mmd`. Notes for the report: ward numbers are unique per area; one active assignment per
complaint is enforced by a nullable unique column; GPS ranges, ratings and confidence values are enforced by database
check constraints; the area is derived from the ward rather than stored twice.
