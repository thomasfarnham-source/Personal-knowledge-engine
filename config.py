# config.py

import os
from dotenv import load_dotenv

# Load environment variables from the .env file into the system environment
load_dotenv()

# Retrieve the Supabase project URL from the environment
SUPABASE_URL = os.getenv("SUPABASE_URL")

# Retrieve the Supabase service role key (used for secure server-side access)
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
