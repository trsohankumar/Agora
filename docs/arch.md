```mermaid
flowchart TB
    subgraph SERVERS
        direction TB
        leader[LEADER Server 1]
        follower1[Server 2 Follower]
        follower2[Server 3 Follower]

        follower1 -->|Heartbeat| leader
        follower2 -->|Heartbeat| leader
        leader -.->|Heartbeat ACK| follower1
        leader -.->|Heartbeat ACK| follower2
        leader -->|Snapshot Marker| follower1
        leader -->|Snapshot Marker| follower2
    end

    subgraph AUCTION ROOM
        direction TB
        c1[Client 1 Auctioneer]
        c2[Client 2 Bidder]
        c3[Client 3 Bidder]
        c1 --- c2
        c2 --- c3
    end

    %% Client to Leader (Unicast)
    c1 -->|BID_SUBMIT| leader
    c2 -->|BID_SUBMIT| leader
    c3 -->|BID_SUBMIT| leader
    
    cn[Client n] -..- |CONNECTED| leader
    


    %% Leader to Clients
    leader -->|ROUND_COMPLETE| c1
    leader -->|ROUND_COMPLETE| c2
    leader -->|ROUND_COMPLETE| c3

    %% Styling
    style leader fill:#4CAF50,stroke:#2E7D32,color:#ffffff,stroke-width:3px
    style follower1 fill:#2196F3,stroke:#1565C0,color:#ffffff
    style follower2 fill:#2196F3,stroke:#1565C0,color:#ffffff
    style c1 fill:#FF9800,stroke:#EF6C00,color:#ffffff
    style c2 fill:#FFC107,stroke:#FF8F00,color:#000000
    style c3 fill:#FFC107,stroke:#FF8F00,color:#000000
    style cn fill:#FFC107,stroke:#FF8F00,color:#000000
