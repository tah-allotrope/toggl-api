# Firebase Blaze Migration Plan: Zero-Cost Alternative

## Problem Statement
Firebase Cloud Functions require Blaze (paid) plan due to:
1. Cloud Build dependency requiring billing enabled
2. Outbound HTTP requests to api.track.toggl.com blocked on Spark plan

## Solution: GitHub Actions (sync) + Vercel (HTTP functions)

This approach splits functions by type:
- **Batch/Toggl sync functions** → GitHub Actions (no timeout, no billing required)
- **Interactive HTTP functions** → Vercel Hobby tier (free, no CC, 60s limit sufficient)

## What Stays Unchanged
- Firebase Hosting (Spark plan - serves SPA)
- Firebase Firestore (Spark plan - data store)
- Firebase Authentication (Spark plan - user login)
- All Python logic in:
  - `sync_engine.py`
  - `data_store.py`
  - `toggl_client.py`
  - `chat_engine.py`
- Firestore rules and indexes

## New Files to Create

### 1. GitHub Actions for Sync
`.github/workflows/sync_quick.yml` - Daily automatic sync
```yaml
name: Daily Quick Sync
on:
  schedule:
    - cron: '0 3 * * *'  # 3am UTC daily
  workflow_dispatch:
jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install firebase-admin requests pandas python-dotenv
      - name: Run sync
        env:
          TOGGL_API_TOKEN: ${{ secrets.TOGGL_API_TOKEN }}
          FIREBASE_SERVICE_ACCOUNT_JSON: ${{ secrets.FIREBASE_SERVICE_ACCOUNT_JSON }}
        run: python scripts/github_sync.py --type quick
```

`.github/workflows/sync_dispatch.yml` - Manual full/enriched sync
```yaml
name: Manual Sync
on:
  workflow_dispatch:
    inputs:
      sync_type:
        description: 'Sync type'
        required: true
        default: 'full'
        options: ['full', 'enriched']
      year:
        description: 'Year for enriched sync (ignored for full/quick)'
        required: false
        type: number
jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install firebase-admin requests pandas python-dotenv
      - name: Run sync
        env:
          TOGGL_API_TOKEN: ${{ secrets.TOGGL_API_TOKEN }}
          FIREBASE_SERVICE_ACCOUNT_JSON: ${{ secrets.FIREBASE_SERVICE_ACCOUNT_JSON }}
        run: python scripts/github_sync.py --type ${{ inputs.sync_type }} --year ${{ inputs.year || '' }}
```

### 2. GitHub Sync Wrapper
`scripts/github_sync.py` - CLI wrapper for sync operations
```python
#!/usr/bin/env python3
"""
GitHub Actions wrapper for Toggl sync operations.
Reads secrets and calls existing sync_engine functions.
"""

import argparse
import json
import os
import sys
from firebase_admin import credentials, firestore, initialize_app

# Add functions directory to path to import existing modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'functions'))

from sync_engine import (
    sync_current_year,
    sync_full,
    sync_enriched_year,
    get_sync_status,
    get_stats
)
from toggl_client import TogglClient

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--type', required=True, choices=['quick', 'full', 'enriched'])
    parser.add_argument('--year', type=int, help='Year for enriched sync')
    args = parser.parse_args()

    # Initialize Firebase from service account JSON
    sa_json = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
    if not sa_json:
        raise ValueError("FIREBASE_SERVICE_ACCOUNT_JSON environment variable required")
    
    sa_info = json.loads(sa_json)
    cred = credentials.Certificate(sa_info)
    initialize_app(cred)
    db = firestore.client()

    # Initialize Toggl client
    token = os.getenv('TOGGL_API_TOKEN')
    if not token:
        raise ValueError("TOGGL_API_TOKEN environment variable required")
    client = TogglClient(api_token=token)

    # Execute requested sync
    if args.type == 'quick':
        result = sync_current_year(client, db)
        print(f"Quick sync completed: {result['entries']} entries")
    elif args.type == 'full':
        earliest_year = 2017  # default from original code
        result = sync_full(client, db, earliest_year)
        print(f"Full sync completed: {result['total_entries']} entries across {result['years_synced']} years")
    elif args.type == 'enriched':
        if args.year is None:
            raise ValueError("--year required for enriched sync")
        result = sync_enriched_year(client, db, args.year)
        print(f"Enriched sync for {args.year}: {result['entries']} entries")

if __name__ == '__main__':
    main()
```

### 3. Vercel HTTP Functions
`api/chat.py` - Chat answer endpoint
```python
from http.server import BaseHTTPRequestHandler
import json
import os
import sys

# Add functions directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'functions'))

from chat_engine import answer_question
from firebase_admin import credentials, firestore, initialize_app

# Initialize Firebase (same as in github_sync.py)
def init_firebase():
    sa_json = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
    if not sa_json:
        raise ValueError("FIREBASE_SERVICE_ACCOUNT_JSON required")
    sa_info = json.loads(sa_json)
    cred = credentials.Certificate(sa_info)
    initialize_app(cred)

# Initialize on import
try:
    init_firebase()
except ValueError:
    # Handle case where env vars not set during build
    pass

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        # Simple auth check (alternative: verify Firebase ID token)
        auth_header = self.headers.get('Authorization')
        expected_token = os.getenv('API_SECRET')
        if not auth_header or not auth_header.startswith('Bearer ') or auth_header[7:] != expected_token:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Unauthorized'}).encode())
            return
        
        db = firestore.client()
        question = data.get('question', '')
        answer = answer_question(db, question)
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'answer': answer}).encode('utf-8'))
```

`api/stats.py` - Statistics endpoint (similar structure)
```python
from http.server import BaseHTTPRequestHandler
import json
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'functions'))

from sync_engine import get_stats
from firebase_admin import credentials, firestore, initialize_app

def init_firebase():
    sa_json = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
    if not sa_json:
        raise ValueError("FIREBASE_SERVICE_ACCOUNT_JSON required")
    sa_info = json.loads(sa_json)
    cred = credentials.Certificate(sa_info)
    initialize_app(cred)

try:
    init_firebase()
except ValueError:
    pass

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        auth_header = self.headers.get('Authorization')
        expected_token = os.getenv('API_SECRET')
        if not auth_header or not auth_header.startswith('Bearer ') or auth_header[7:] != expected_token:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Unauthorized'}).encode())
            return
        
        db = firestore.client()
        stats = get_stats(db)
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(stats).encode('utf-8'))
```

`api/status.py` - Sync status endpoint
```python
from http.server import BaseHTTPRequestHandler
import json
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'functions'))

from sync_engine import get_sync_status
from firebase_admin import credentials, firestore, initialize_app

def init_firebase():
    sa_json = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
    if not sa_json:
        raise ValueError("FIREBASE_SERVICE_ACCOUNT_JSON required")
    sa_info = json.loads(sa_json)
    cred = credentials.Certificate(sa_info)
    initialize_app(cred)

try:
    init_firebase()
except ValueError:
    pass

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        auth_header = self.headers.get('Authorization')
        expected_token = os.getenv('API_SECRET')
        if not auth_header or not auth_header.startswith('Bearer ') or auth_header[7:] != expected_token:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Unauthorized'}).encode())
            return
        
        db = firestore.client()
        status = get_sync_status(db)
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(status).encode('utf-8'))
```

### 4. Vercel Configuration
`vercel.json` - Routes and runtime configuration
```json
{
  "functions": {
    "api/chat.py": {
      "runtime": "python3.12"
    },
    "api/stats.py": {
      "runtime": "python3.12"
    },
    "api/status.py": {
      "runtime": "python3.12"
    }
  },
  "routes": [
    { "src": "/chat", "dest": "/api/chat.py" },
    { "src": "/stats", "dest": "/api/stats.py" },
    { "src": "/status", "dest": "/api/status.py" }
  ]
}
```

`api/requirements.txt` - Dependencies
```
firebase-admin>=6.4.0
requests>=2.31.0
pandas>=2.1.0
python-dotenv>=1.0.0
```

## Frontend Changes
`frontend/src/main.js` - Replace Firebase callable functions with fetch to Vercel

Replace:
```javascript
import { getFunctions, httpsCallable } from "firebase/functions";
// ...
const functions = getFunctions(app);
const chatAnswer = httpsCallable(functions, "chat_answer");
// const answer = (await chatAnswer({ question })).data.answer;
```

With:
```javascript
const API_SECRET = localStorage.getItem('api_secret') || ''; // Set on login
// ...
const response = await fetch('https://your-project.vercel.app/chat', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${API_SECRET}`
  },
  body: JSON.stringify({ question })
});
const data = await response.json();
const answer = data.answer;
```

Apply similar changes for `/stats` and `/status` endpoints.

## Secrets Configuration

### GitHub Repository Secrets
- `TOGGL_API_TOKEN`: Your Toggl API token
- `FIREBASE_SERVICE_ACCOUNT_JSON`: Firebase service account key JSON

### Vercel Environment Variables
- `TOGGL_API_TOKEN`: Same Toggl token
- `FIREBASE_SERVICE_ACCOUNT_JSON`: Same service account JSON
- `API_SECRET`: Random string for endpoint authentication (also set in frontend localStorage)

## Migration Steps

1. Generate Firebase service account key
2. Add GitHub secrets
3. Create `scripts/github_sync.py`
4. Create GitHub Actions workflows
5. Test sync manually via GitHub Actions
6. Create Vercel project and connect repo
7. Add Vercel env vars
8. Create `api/` directory with function files
9. Add `vercel.json` and `api/requirements.txt`
10. Update frontend to call Vercel endpoints
11. Deploy frontend: `firebase deploy --only hosting`
12. Remove `functions/` from `firebase.json` once verified
13. Deploy to Vercel: `vercel --prod`

## Rollback Plan
If issues occur:
1. Frontend changes can be reverted easily
2. Vercel functions can be deleted/disabled
3. GitHub Actions can be disabled
4. Original Cloud Functions remain intact in `functions/` until step 12

## Cost Analysis
- **GitHub Actions**: ~150 compute minutes/month (well under 2,000 free min for private repos)
- **Vercel Hobby**: Free forever, no credit card required
- **Firebase Hosting/Firestore/Auth**: Remain on Spark (free) plan
- **Total ongoing cost**: $0.00

## Benefits
- Zero dollars spent, no credit card required
- Maintains identical functionality
- Leverages existing Python code with minimal changes
- GitHub Actions provides reliable scheduled sync
- Vercel provides low-latency HTTP endpoints for interactive use