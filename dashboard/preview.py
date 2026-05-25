"""Local preview launcher — patches services.api_client with mock data."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import services.api_client_mock as _mock
sys.modules['services.api_client'] = _mock

# Run the real app
exec(open(os.path.join(os.path.dirname(__file__), 'app.py')).read())
