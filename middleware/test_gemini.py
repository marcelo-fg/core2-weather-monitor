import google.generativeai as genai
import yaml

with open('/Users/marcelogoncalves/Cloud-and-Advanced-Analytics/core2_project/middleware/env-vars.yaml', 'r') as f:
    env = yaml.safe_load(f)
    api_key = env['GEMINI_API_KEY']

genai.configure(api_key=api_key)
for m in genai.list_models():
    print(m.name, m.supported_generation_methods)
