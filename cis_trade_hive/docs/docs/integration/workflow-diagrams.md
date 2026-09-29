# Workflow Diagrams

Visual representations of key workflows.

## Portfolio Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Draft: Create
    Draft --> PendingApproval: Submit
    PendingApproval --> Active: Approve
    PendingApproval --> Rejected: Reject
    Rejected --> Draft: Edit
    Active --> Closed: Close
    Closed --> Active: Reactivate
    Closed --> [*]
```

## Four-Eyes Workflow

```mermaid
sequenceDiagram
    participant M as Maker
    participant S as System
    participant C as Checker

    M->>S: Create Portfolio (Draft)
    S-->>M: Saved
    M->>S: Submit for Approval
    S->>S: Validate (Maker ≠ Checker)
    S->>C: Notify Pending Approval
    C->>S: Review Portfolio
    alt Approve
        C->>S: Approve with Comments
        S->>S: Status = Active
        S-->>M: Notification (Approved)
    else Reject
        C->>S: Reject with Reason
        S->>S: Status = Rejected
        S-->>M: Notification (Rejected)
        M->>S: Edit & Resubmit
    end
```

## Authentication Flow

```mermaid
graph TD
    A[User enters Login ID] --> B{Query ACL User Table}
    B -->|Not Found| C[Display Error]
    B -->|Found| D{User Enabled?}
    D -->|No| C
    D -->|Yes| E[Query User Group]
    E --> F[Query Group Permissions]
    F --> G[Build Permission Map]
    G --> H[Create Session]
    H --> I[Redirect to Dashboard]
```

## Data Sync Flow

```mermaid
graph LR
    A[GMP System] -->|2:00 AM| B[CSV Export]
    B -->|SFTP| C[Shared Directory]
    C -->|Hive External| D[Impala Tables]
    D -->|Query| E[CisTrade App]
    E -->|Display| F[User Browser]
```

## FX Rate Update

```mermaid
sequenceDiagram
    participant B as Bloomberg
    participant S as CisTrade Service
    participant K as Kudu
    participant P as Portfolios

    loop Every 15 minutes
        S->>B: Request Latest Rates
        B-->>S: Rate Data
        S->>S: Validate Rates
        S->>K: Update FX Rate Table
        K-->>S: Success
        S->>P: Trigger NAV Recalculation
        P->>P: Calculate New NAV
    end
```

## UDF Value Update

```mermaid
graph TD
    A[User Enters New Value] --> B{Validate Data Type}
    B -->|Invalid| C[Show Error]
    B -->|Valid| D{Check Effective Date}
    D -->|Overlaps| C
    D -->|Valid| E[End-Date Previous Value]
    E --> F[Insert New Value]
    F --> G[Record in History]
    G --> H[Log Audit]
    H --> I[Success Message]
```

## Approval Decision Tree

```mermaid
graph TD
    A[Pending Approval] --> B{Checker Reviews}
    B -->|Approve| C{Same User?}
    C -->|Yes| D[Error: Self-Approval]
    C -->|No| E{Comments Provided?}
    E -->|No| F[Error: Comments Required]
    E -->|Yes| G[Status = Active]
    G --> H[Notify Maker]
    B -->|Reject| I{Reason Provided?}
    I -->|No| F
    I -->|Yes| J[Status = Rejected]
    J --> K[Notify Maker]
```

## System Architecture

```mermaid
graph TB
    subgraph "Presentation Layer"
        A[Web Browser]
    end

    subgraph "Application Layer"
        B[Django Views]
        C[Service Layer]
    end

    subgraph "Data Layer"
        D[Repository Layer]
        E[Impala Connection]
    end

    subgraph "Storage Layer"
        F[Kudu Tables]
        G[Hive External Tables]
    end

    A <--> B
    B <--> C
    C <--> D
    D <--> E
    E <--> F
    E <--> G
```

## Audit Logging Flow

```mermaid
graph LR
    A[User Action] --> B[Django View]
    B --> C[Extract Context]
    C --> D{Significant Action?}
    D -->|No| E[Continue]
    D -->|Yes| F[Audit Repository]
    F --> G[Build Audit Record]
    G --> H[Insert to Kudu]
    H --> E
```

## Report Generation

```mermaid
sequenceDiagram
    participant U as User
    participant V as View
    participant S as Service
    participant R as Repository
    participant E as Export

    U->>V: Request Report
    V->>S: Get Data
    S->>R: Query Database
    R-->>S: Data
    S->>E: Generate Report
    E-->>U: Download File (CSV/PDF/Excel)
```

## Related Documentation

- [Business Processes](business-processes.md)
- [Data Flow](data-flow.md)
- [Architecture](../technical/architecture.md)
