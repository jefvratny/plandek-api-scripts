#!/usr/bin/env python3
"""
GitHub Action for sending test metrics to Plandek Timeseries API.

This script processes test results and sends them to the Plandek Timeseries API
for tracking and analysis. It creates a timeseries for each metric if it doesn't
already exist and then adds the datapoints.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

import requests
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file if it exists
load_dotenv()

class TimeseriesAPIError(Exception):
    """Custom exception for Timeseries API errors"""
    pass

class TimeseriesAPI:
    """Client for interacting with the Plandek Timeseries API."""
    
    def __init__(self, api_key: str = None, base_url: str = None):
        """Initialize the Timeseries API client.
        
        Args:
            api_key: Plandek API key. If not provided, will be read from TIMESERIES_API_KEY env var.
            base_url: Base URL for the API. Defaults to Plandek's production API.
        """
        self.base_url = base_url or os.getenv(
            "TIMESERIES_API_URL",
            "https://api.plandek.com/timeseries/v1"
        ).rstrip('/')
        
        self.api_key = api_key or os.getenv("TIMESERIES_API_KEY")
        if not self.api_key:
            raise ValueError("TIMESERIES_API_KEY environment variable is required")
        
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make an HTTP request to the API."""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.request(method, url, **kwargs)
            
            if response.status_code == 401:
                raise TimeseriesAPIError("Authentication failed. Please check your API key.")
            
            response.raise_for_status()
            return response.json() if response.content else {}
            
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg = f"{e}: {error_data.get('message', 'No error details')}"
                except ValueError:
                    error_msg = f"{e}: {e.response.text}"
            raise TimeseriesAPIError(f"API request failed: {error_msg}") from e
    
    def ensure_timeseries_exists(self, name: str) -> Dict[str, Any]:
        """Ensure a timeseries exists, creating it if necessary."""
        try:
            # Try to get the timeseries by name
            return self._make_request("GET", f"/timeseries_by_name/{name}")
        except TimeseriesAPIError as e:
            if "Not Found" in str(e):
                # Timeseries doesn't exist, create it with just the name
                logger.info(f"Creating new timeseries: {name}")
                return self._make_request(
                    "POST",
                    "/timeseries",
                    json={"name": name}
                )
            raise
    
    def add_datapoints(self, timeseries_name: str, datapoints: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Add datapoints to a timeseries.
        
        Args:
            timeseries_name: Name of the timeseries to add datapoints to
            datapoints: List of datapoint dictionaries with 'timestamp' and 'value' keys
            
        Returns:
            API response
        """
        # Ensure the timeseries exists
        timeseries = self.ensure_timeseries_exists(timeseries_name)
        timeseries_id = timeseries["timeseries_id"]
        
        # Prepare datapoints in the expected format
        formatted_datapoints = []
        for dp in datapoints:
            # Ensure timestamp has timezone information
            timestamp = dp["timestamp"]
            if not timestamp.endswith('Z') and not ('+' in timestamp or timestamp.endswith('Z')):
                timestamp = f"{timestamp}Z"  # Assume UTC if no timezone specified
                
            formatted_datapoints.append({
                "timestamp": timestamp,
                "value": float(dp["value"])  # Ensure value is a float
            })
        
        # Add datapoints to the timeseries (limit of 1000 per request)
        return self._make_request(
            "POST",
            f"/timeseries/{timeseries_id}/datapoints",
            json=formatted_datapoints
        )

def parse_test_results(test_results: str) -> Dict[str, Any]:
    """Parse test results and extract relevant metrics.
    
    Args:
        test_results: JSON string containing test results
        
    Returns:
        Dictionary containing test metrics with datapoints grouped by timeseries name
    """
    try:
        test_data = json.loads(test_results)
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Calculate metrics
        total = test_data.get("tests", 0)
        passed = test_data.get("passed", 0)
        failed = test_data.get("failed", 0)
        skipped = test_data.get("skipped", 0)
        duration = test_data.get("duration", 0)
        success_rate = (passed / total * 100) if total > 0 else 0
        
        # Get repository and workflow context
        repo = os.getenv("GITHUB_REPOSITORY", "unknown").replace('/', '.')
        workflow = os.getenv("GITHUB_WORKFLOW", "unknown").replace(' ', '_').lower()
        run_id = os.getenv("GITHUB_RUN_ID", "")
        
        # Create datapoints for each metric
        datapoints = [
            # Test counts
            {"name": f"{repo}.tests.total", "value": total, "timestamp": timestamp},
            {"name": f"{repo}.tests.passed", "value": passed, "timestamp": timestamp},
            {"name": f"{repo}.tests.failed", "value": failed, "timestamp": timestamp},
            {"name": f"{repo}.tests.skipped", "value": skipped, "timestamp": timestamp},
            
            # Derived metrics
            {"name": f"{repo}.tests.success_rate", "value": success_rate, "timestamp": timestamp},
            {"name": f"{repo}.tests.duration_seconds", "value": duration, "timestamp": timestamp},
            
            # Workflow context (as a separate timeseries)
            {"name": f"{repo}.workflow", "value": 1, "timestamp": timestamp}
        ]
        
        return {
            "timestamp": timestamp,
            "repository": repo,
            "workflow": workflow,
            "run_id": run_id,
            "datapoints": datapoints
        }
        
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Error parsing test results: {e}")
        raise ValueError(f"Invalid test results format: {e}") from e

def send_test_metrics(test_results: str, api_key: str = None, base_url: str = None) -> Dict[str, Any]:
    """Parse test results and send them to the Timeseries API.
    
    Args:
        test_results: JSON string containing test results
        api_key: Optional API key (will use TIMESERIES_API_KEY env var if not provided)
        base_url: Optional base URL for the API
        
    Returns:
        Dictionary with results of the operation
    """
    try:
        # Parse test results
        metrics = parse_test_results(test_results)
        logger.info(f"Parsed test metrics for {metrics['repository']}")
        
        # Initialize API client
        api = TimeseriesAPI(api_key=api_key, base_url=base_url)
        
        # Send each datapoint to the API
        results = {}
        for datapoint in metrics["datapoints"]:
            timeseries_name = datapoint["name"]
            point_data = {
                "timestamp": datapoint["timestamp"],
                "value": datapoint["value"]
            }
            
            try:
                result = api.add_datapoints(timeseries_name, [point_data])
                results[timeseries_name] = "success"
                logger.debug(f"Sent datapoint for {timeseries_name}")
            except TimeseriesAPIError as e:
                results[timeseries_name] = f"error: {str(e)}"
                logger.error(f"Failed to send datapoint for {timeseries_name}: {e}")
        
        return {
            "success": True,
            "timestamp": metrics["timestamp"],
            "repository": metrics["repository"],
            "workflow": metrics["workflow"],
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Error sending test metrics: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def main():
    """Main entry point for the script."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Send test results to Plandek Timeseries API')
    parser.add_argument('test_results', type=str, help='JSON string containing test results')
    parser.add_argument('--api-key', type=str, help='Plandek API key (or set TIMESERIES_API_KEY env var)')
    parser.add_argument('--base-url', type=str, help='Base URL for the API')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.debug:
        logger.setLevel(logging.DEBUG)
    
    try:
        result = send_test_metrics(
            test_results=args.test_results,
            api_key=args.api_key,
            base_url=args.base_url
        )
        
        if result["success"]:
            print(f"Successfully sent test metrics for {result['repository']}")
            for metric, status in result["results"].items():
                print(f"  {metric}: {status}")
            sys.exit(0)
        else:
            print(f"Error: {result.get('error', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)
            
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
