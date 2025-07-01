# GitHub Action for Test Results to Plandek Timeseries API

This GitHub Action processes test results and sends them to Plandek's Timeseries API for tracking and analysis.

## Features

- Processes test results from JUnit XML format using `dorny/test-reporter`
- Extracts key metrics (total tests, passed, failed, skipped, success rate, duration)
- Creates timeseries in Plandek if they don't exist
- Includes repository and workflow context with each data point
- Handles authentication and error reporting

## Setup

1. Add the following secret to your GitHub repository:
   - `TIMESERIES_API_KEY`: Your API key for Plandek's Timeseries API

2. Configure the following variables (optional):
   - `TIMESERIES_API_URL`: Base URL for the timeseries API (defaults to `https://api.plandek.com/timeseries/v1`)

## Usage

1. Copy the workflow file to your repository:
   ```bash
   mkdir -p .github/workflows/
   cp timeseries-api/testing-data-github-actions/.github/workflows/process-test-results.yml .github/workflows/
   ```

2. Copy the script to your repository:
   ```bash
   mkdir -p .github/scripts/
   cp timeseries-api/testing-data-github-actions/.github/scripts/process_test_metrics.py .github/scripts/
   ```

3. The workflow will automatically run after your test workflow completes. Make sure to update the workflow trigger to match your test workflow name:

```yaml
on:
  workflow_run:
    workflows: ["Your Test Workflow Name"]
    types:
      - completed
```

## Example Workflow

Here's how the workflow is structured:

```yaml
name: Process Test Results

on:
  workflow_run:
    workflows: ["Run Tests"]  # Replace with your test workflow name
    types:
      - completed

jobs:
  process-test-results:
    name: Process Test Results
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'
        
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install requests python-dotenv
    
    - name: Get test results
      id: test-results
      uses: dorny/test-reporter@v1
      with:
        name: Test Results
        path: test-results/**/*.xml  # Update this path to match your test results location
        reporter: java-junit
        fail-on-error: false
    
    - name: Process and send test metrics
      env:
        TIMESERIES_API_KEY: ${{ secrets.TIMESERIES_API_KEY }}
        TIMESERIES_API_URL: ${{ vars.TIMESERIES_API_URL || 'https://api.plandek.com/timeseries/v1' }}
      run: |
        python .github/scripts/process_test_metrics.py "${{ steps.test-results.outputs.data }}"

## Data Format

The script creates separate timeseries for each metric, with the following naming convention:
- `{repository}.tests.total`
- `{repository}.tests.passed`
- `{repository}.tests.failed`
- `{repository}.tests.skipped`
- `{repository}.tests.success_rate`
- `{repository}.tests.duration_seconds`
- `{repository}.workflow`

### API Usage

The integration works as follows:

1. **Timeseries Creation**:
   - Each timeseries is created with just a name
   - The API will automatically create the timeseries when the first datapoint is added

2. **Datapoint Format**:
   - Each datapoint must have a `timestamp` (ISO 8601 with timezone, e.g., `2023-01-01T12:00:00Z`)
   - The `value` must be a number (integer or float)
   - Multiple datapoints can be sent in a single API call (up to 1000 per request)

### Example API Payloads

For a repository named `owner/repo` and workflow `CI Tests`, the script will make separate API calls for each timeseries. Here are examples of the API requests:

1. **Creating the timeseries (if it doesn't exist)**:
   ```json
   POST /timeseries
   {
     "name": "owner.repo.tests.total"
   }
   ```

2. **Adding datapoints to the timeseries**:
   ```json
   POST /timeseries/{timeseries_id}/datapoints
   [
     {
       "timestamp": "2023-01-01T12:00:00Z",
       "value": 100
     }
   ]
   ```

3. **Workflow context (as a separate timeseries)**:
   ```json
   POST /timeseries
   {
     "name": "owner.repo.workflow"
   }
   
   POST /timeseries/{workflow_timeseries_id}/datapoints
   [
     {
       "timestamp": "2023-01-01T12:00:00Z",
       "value": 1
     }
   ]
   ```

The script handles all of this automatically - you just need to provide the test results.

```json
[
  {
    "timestamp": "2023-01-01T12:00:00Z",
    "value": 100
  },
  {
    "timestamp": "2023-01-01T12:00:00Z",
    "value": 95
  }
]
```

Each timeseries is identified by its name (e.g., `owner.repo.tests.passed`). You can add up to 1,000 datapoints to a timeseries in a single API call. The API will create the timeseries automatically if it doesn't exist.

The script creates a separate timeseries named `{repository}.workflow` with a value of `1` to track workflow executions.

## Customization

You can customize the following aspects of the integration:

1. **Test Results Format**: The script expects test results in a specific JSON format. Modify the `parse_test_results` function in `process_test_metrics.py` to match your test runner's output format.

2. **Timeseries Naming**: The default naming convention is `{repository}.{metric_name}`. You can modify the `parse_test_results` function to use a different naming scheme if needed.

3. **API Configuration**: 
   - Set `TIMESERIES_API_URL` to override the default API endpoint
   - Set `TIMESERIES_API_KEY` to provide your authentication token

4. **Workflow Triggers**: The GitHub Actions workflow can be triggered on different events by modifying the `on` section in the workflow file.

## Requirements

- Python 3.8+
- `requests` and `python-dotenv` packages (installed automatically by the workflow)
