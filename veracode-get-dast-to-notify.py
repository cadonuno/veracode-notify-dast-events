from veracode_api_py import Analyses, BusinessUnits
from veracode_api_py.apihelper import APIHelper
from datetime import datetime
from datetime import timedelta
import argparse

MAXIMUM_SCAN_DURATION = 25 # a DAST scan can run for up to 25 days

urls_cache = dict()
ANALYSIS_CACHE = dict()
DATE_TIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'

date_interval_days = 1
today = None
previous_day = None
# a scan can run for up to 25 days, so we need to look back that far plus our interval to ensure we capture all scans
oldest_possible_scan_date = None
next_day = None



def parse_datetime(date_string):
    if "[" in date_string and "]" in date_string:
        return date_string[:date_string.index("[")]
    return datetime.strptime(date_string, DATE_TIME_FORMAT).strftime(DATE_TIME_FORMAT)

def get_start_date(occurrence):
    return parse_datetime(occurrence["start_date"]) if "start_date" in occurrence else None

def get_create_date(base_analysis):
    return parse_datetime(base_analysis["created_on"]) if "created_on" in base_analysis else None

def get_end_date(occurrence):
    return parse_datetime(occurrence["end_date"]) if "end_date" in occurrence else None

def get_status(occurrence):
    if "status" in occurrence and "status_type" in occurrence["status"]:
        return occurrence["status"]["status_type"]
    return 'No status found'


def get_urls_for_id(analysis_id):
    if analysis_id in urls_cache:
        return urls_cache.get(analysis_id)
    
    #scans are the URLs for each analysis
    scans = Analyses().get_scans(analysis_id)
    urls_isms = ", ".join([scan["target_url"] for scan in scans])
    urls_cache.update({analysis_id: urls_isms})
    return urls_isms

def get_analysis_for_id(analysis_id):
    if analysis_id in ANALYSIS_CACHE:
        return ANALYSIS_CACHE.get(analysis_id)
    analyses = Analyses().get(analysis_id)
    ANALYSIS_CACHE.update({analysis_id: analyses})
    return analyses

def parse_occurrence(occurrence):
    analysis = get_analysis_for_id(occurrence["analysis_id"])
    return {
        "analysis_id": occurrence["analysis_id"],
        "analysis_occurrence_id": occurrence["analysis_occurrence_id"],
        "analysis_name": analysis["name"],
        "business_unit": analysis["org_info"]["business_unit_id"],
        "owner": analysis["org_info"]["owner"],
        "urls": get_urls_for_id(occurrence["analysis_id"]),
        "start_date": get_start_date(occurrence),
        "end_date": get_end_date(occurrence),
        "status": get_status(occurrence)
    }

def parse_occurrences(all_occurrences):
    return [parse_occurrence(occurrence) for occurrence in all_occurrences]

def get_scan_ocurrences(available_scans, base_filters):    
    found_scans = []
    for scan in available_scans:
        if "analysis_id" not in scan:
            continue
        scan_filters = base_filters.copy()
        scan_filters["analysis_id"] = scan["analysis_id"]
        found_scans += APIHelper()._rest_paged_request('was/configservice/v1/analysis_occurrences','GET','analysis_occurrences', scan_filters)
    return found_scans

def get_starting_scans(available_scans=[]):
    global date_interval_days, previous_day, next_day, oldest_possible_scan_date, today
    scan_filters = {"start_date_after": today.strftime(DATE_TIME_FORMAT), "start_date_before": next_day.strftime(DATE_TIME_FORMAT)} 

    all_occurrences = get_scan_ocurrences(available_scans, scan_filters)
    if all_occurrences:
        print(f"Starting to process {len(all_occurrences)} scans starting in the next 24 hours")
        return parse_occurrences(all_occurrences)

    return []

def get_failed_scans(available_scans=[]):
    global date_interval_days, previous_day, next_day, oldest_possible_scan_date, today
    scan_filters = {"status": ["VERIFICATION_FAILED", "STOPPED", "SUBMIT_FAILED", "STOPPING_SAVING_RESULT",
                               "STOPPING_DELETING_RESULT", "STOPPED_TIME", "STOPPED_TIME_VERIFYING_RESULTS", 
                               "STOPPED_TECHNICAL_ISSUE", "STOPPED_VERIFYING_RESULTS_BY_USER", "STOPPED_VERIFYING_RESULTS", 
                               "SCAN_ERROR_VERIFYING_PARTIAL_RESULTS", "KILLED_VERIFYING_PARTIAL_RESULTS", "STOPPED_PARTIAL_RESULTS_AVAILABLE", 
                               "SCAN_ERROR_PARTIAL_RESULTS_AVAILABLE", "KILLED_PARTIAL_RESULTS_AVAILABLE", "TIME_EXPIRED_PARTIAL_RESULTS_AVAILABLE"], 
                    "start_date_after": oldest_possible_scan_date.strftime(DATE_TIME_FORMAT), "start_date_before": today.strftime(DATE_TIME_FORMAT)} 


    all_occurrences = get_scan_ocurrences(available_scans, scan_filters)
    if all_occurrences:
        print(f"Starting to process {len(all_occurrences)} POTENTIAL scans failed in the last 24 hours")
        return [occurrence for occurrence in parse_occurrences(all_occurrences) if previous_day >= datetime.strptime(occurrence["end_date"], DATE_TIME_FORMAT)]
    return []

def get_finished_scans(available_scans=[]):
    global date_interval_days, previous_day, next_day, oldest_possible_scan_date, today

    scan_filters = {"status": ["FINISHED_VERIFYING_RESULTS", "FINISHED_RESULTS_AVAILABLE"], "start_date_after": oldest_possible_scan_date.strftime(DATE_TIME_FORMAT), "start_date_before": today.strftime(DATE_TIME_FORMAT)} 
    all_occurrences = get_scan_ocurrences(available_scans, scan_filters)
    if all_occurrences:
        print(f"Starting to process {len(all_occurrences)} POTENTIAL scans finished in the last 24 hours")
        return [occurrence for occurrence in parse_occurrences(all_occurrences) if previous_day >= datetime.strptime(occurrence["end_date"], DATE_TIME_FORMAT)]
    return []

def build_scan_starting_email(starting_scan_occurrence):
    return {
        "to": starting_scan_occurrence["owner"],
        "subject": f"Veracode DAST Scan Started: {starting_scan_occurrence['analysis_name']}",
        "body": f"""Hello, your Veracode scan of URLs {starting_scan_occurrence['urls']} is starting at {starting_scan_occurrence['start_date']}
        You can find more details in the Veracode Platform: https://web.analysiscenter.veracode.com/was/#/analysisoccurrence/{starting_scan_occurrence["analysis_occurrence_id"]}/scans"""
    }

def build_scan_finished_email(finished_scan_occurrence):
    return {
        "to": finished_scan_occurrence["owner"],
        "subject": f"Veracode DAST Scan Finished: {finished_scan_occurrence['analysis_name']}",
        "body": f"""Hello, your Veracode scan of URLs {finished_scan_occurrence['urls']} finished at {finished_scan_occurrence['end_date']}
        You can find more details in the Veracode Platform: https://web.analysiscenter.veracode.com/was/#/analysisoccurrence/{finished_scan_occurrence["analysis_occurrence_id"]}/scans"""
    }

def build_scan_failed_email(failed_scan_occurrence):
    return {
        "to": failed_scan_occurrence["owner"],
        "subject": f"Veracode DAST Scan Failed: {failed_scan_occurrence['analysis_name']}",
        "body": f"""Hello, your Veracode scan of URLs {failed_scan_occurrence['urls']} failed at {failed_scan_occurrence['end_date']}
        You can find more details in the Veracode Platform: https://web.analysiscenter.veracode.com/was/#/analysisoccurrence/{failed_scan_occurrence["analysis_occurrence_id"]}/scans"""
    }

def send_notification(occurrence):
    print("Sending e-mail to:", occurrence["to"])
    print("Subject:", occurrence["subject"])
    print("Body:", occurrence["body"])
    
    #TODO: implement e-mail sending
    return None

def main():
    parser = argparse.ArgumentParser(description='Get DAST events to notify')
    parser.add_argument('--date_interval_days', type=int, default=1, help='Number of days to look back and forward for scans (default: 1)')
    parser.add_argument('--scan_name_filter', type=str, help='Filter scans by name containing this string')
    args = parser.parse_args()
    scan_name_filter = args.scan_name_filter

    if args.date_interval_days:
        global date_interval_days, previous_day, next_day, oldest_possible_scan_date, today
        date_interval_days = args.date_interval_days
        today = datetime.now()
        previous_day = today - timedelta(days=date_interval_days)
        next_day = today + timedelta(days=date_interval_days)
        oldest_possible_scan_date = today - timedelta(days=MAXIMUM_SCAN_DURATION+date_interval_days)

    available_scans = Analyses().get_by_name(scan_name_filter) if scan_name_filter else Analyses().get_all()

    business_unit_map = dict()
    for bu in BusinessUnits().get_all():
        business_unit_map.update({str(bu["bu_legacy_id"]): bu["bu_name"]})
        
    all_starting_scans = [build_scan_starting_email(occurrence) for occurrence in get_starting_scans(available_scans)]
    all_finished_scans = [build_scan_finished_email(occurrence) for occurrence in get_finished_scans(available_scans)]
    all_failed_scans = [build_scan_failed_email(occurrence) for occurrence in get_failed_scans(available_scans)]

    emails_to_end = all_starting_scans + all_finished_scans + all_failed_scans

    for occurrence in emails_to_end:
        send_notification(occurrence)



if __name__ == '__main__':
    main()