import re
from concurrent import futures

from requests.auth import HTTPBasicAuth
from sumoappclient.common.utils import convert_epoch_to_utc_date, convert_utc_date_to_epoch
from sumoappclient.sumoclient.base import BaseAPI
from sumoappclient.sumoclient.factory import OutputHandlerFactory
from sumoappclient.sumoclient.httputils import ClientMixin


class JFrogXrayAPI(BaseAPI):
    MOVING_WINDOW_DELTA = 1
    DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
    DATE_FORMAT_SUMO_LOGIC_TO_MATCH_WEBHOOK = "%Y-%m-%dT%H:%M:%S.%sZ"

    def __init__(self, kvstore, config):
        super(JFrogXrayAPI, self).__init__(kvstore, config)

        # Set JFrog Xray configuration
        self.api_config = self.config['JFrogXray']
        # Create Token to be used for API call.
        self.token = HTTPBasicAuth(username=self.api_config["USERNAME"], password=self.api_config["PASSWORD"])

        # Create Violations URL from Host and Port
        self.url = "http://" + self.api_config["HOSTNAME"] + ":" + str(self.api_config["PORT"]) + self.api_config[
            "VIOLATION_URL"]

    def get_window(self, last_time_utc):
        start_time_epoch = convert_utc_date_to_epoch(last_time_utc,
                                                     date_format=self.DATE_FORMAT) + self.MOVING_WINDOW_DELTA
        return convert_epoch_to_utc_date(start_time_epoch, date_format=self.DATE_FORMAT)


# Fetch Method to get all violation
# 1. Fetch the violation for a specific offset and created date.
# 2. If Fetch is success, then go to step 3 else log the error and keep the current state.
# 3. Transform the data and if the records are zero then Step 4 else step 5.
# 4. If last record date is present, update state else add delta window to created date.
# 5. Send the data and if send success step 6 else keep the current state
# 6. check if more data is present and update the state with new offset and same created date.

class FetchPaginatedDataBasedOnOffset(JFrogXrayAPI):

    def fetch(self):
        output_handler = OutputHandlerFactory.get_handler(self.collection_config['OUTPUT_HANDLER'],
                                                          config=self.config)
        data = self.build_fetch_params()
        sess = ClientMixin.get_new_session()
        next_request = True
        page_counter = 0
        record_counter = 0
        last_record_fetched_date = data["filters"]["created_from"]

        try:
            while next_request:
                send_success = has_more_data = False
                fetch_success, result = ClientMixin.make_request(self.url, method="post", session=sess, logger=self.log,
                                                                 TIMEOUT=self.collection_config['TIMEOUT'],
                                                                 MAX_RETRY=self.collection_config['MAX_RETRY'],
                                                                 BACKOFF_FACTOR=self.collection_config[
                                                                     'BACKOFF_FACTOR'],
                                                                 json=data,
                                                                 auth=self.token,
                                                                 headers={"content-type": "application/json"})
                if fetch_success:
                    data_to_be_sent = self.transform_data(result)
                    if len(data_to_be_sent) > 0:
                        has_more_data = self.has_more_data(result)
                        send_success = output_handler.send(data_to_be_sent, **self.build_send_params())
                        if send_success:
                            page_counter += 1
                            record_counter += len(data_to_be_sent)
                            last_record_fetched_date = result["violations"][-1]["created"]
                            self.log.debug("Successfully sent LogType Violations, Offset %s, Created_from %s",
                                           data["pagination"]["offset"], data["filters"]["created_from"])

                            if has_more_data:
                                data["pagination"]["offset"] = data["pagination"]["offset"] + 1
                                self.save_state(
                                    {"offset": data["pagination"]["offset"],
                                     "last_fetched_created_from": data["filters"]["created_from"]})
                            else:
                                self.save_state(
                                    {"last_fetched_created_from": self.get_window(last_record_fetched_date)})
                        else:
                            self.log.warning("Failed to sent LogType Violations, Offset %s, Created_from %s",
                                             data["pagination"]["offset"], data["filters"]["created_from"])
                    else:
                        self.log.debug("No Result fetched for LogType Violations, Offset %s, Created_from %s",
                                       data["pagination"]["offset"], data["filters"]["created_from"])
                        # If the violations is ZERO than update the window & remove offset.
                        if last_record_fetched_date:
                            self.save_state(
                                {"last_fetched_created_from": self.get_window(last_record_fetched_date)})
                else:
                    self.log.warning("Fetch failed for LogType Violations, Offset %s, Created_from %s",
                                     data["pagination"]["offset"], data["filters"]["created_from"])

                # Check for next request
                next_request = fetch_success and send_success and has_more_data and self.is_time_remaining()

        except Exception as exc:
            self.log.error("Error Occurred while fetching LogType Violations, Offset %s, Created_from %s",
                           data["pagination"]["offset"], data["filters"]["created_from"])
        finally:
            output_handler.close()
        self.log.info("Completed LogType Violations Pages: %s, Records %s", page_counter,
                      record_counter)

    def has_more_data(self, result):
        if "total_violations" in result:
            total_violations = result["total_violations"]
            violations = result["violations"]
            if total_violations - len(violations) > 0:
                return True

        return False


class ViolationsLogsAPI(FetchPaginatedDataBasedOnOffset):

    def __init__(self, kvstore, config):
        super(ViolationsLogsAPI, self).__init__(kvstore, config)

    def get_key(self):
        return "Violations"

    def save_state(self, state):
        self.kvstore.set(self.get_key(), state)

    def get_state(self):
        key = self.get_key()
        if not self.kvstore.has_key(key):
            self.save_state({"last_fetched_created_from": convert_epoch_to_utc_date(self.DEFAULT_START_TIME_EPOCH,
                                                                                    date_format=self.DATE_FORMAT)})
        obj = self.kvstore.get(key)
        return obj

    def build_fetch_params(self):
        filters = {}
        pagination = {"order_by": "created", "limit": 100, "offset": 1}
        current_state = self.get_state()

        if "last_fetched_created_from" in current_state:
            filters["created_from"] = current_state["last_fetched_created_from"]
        if "offset" in current_state:
            pagination["offset"] = current_state["offset"]

        return {"filters": filters, "pagination": pagination}

    def build_send_params(self):
        return {
            "endpoint_key": "HTTP_LOGS_ENDPOINT"
        }

    # fetch CVE details for each violation and add it to current data.
    def transform_data(self, content):
        data_to_be_sent = []
        if content and "violations" in content:
            violations = content["violations"]
            all_futures = {}
            self.log.debug("spawning %d workers" % self.config['Collection']['NUM_WORKERS'])
            with futures.ThreadPoolExecutor(max_workers=self.config['Collection']['NUM_WORKERS']) as executor:
                results = {executor.submit(self.get_violations_details, violation): violation for violation in
                           violations}
                all_futures.update(results)
            for future in futures.as_completed(all_futures):
                param = all_futures[future]
                api_type = str(param)
                try:
                    data = future.result()
                    if data:
                        for value in data:
                            data_to_be_sent.append(value)
                except Exception as exc:
                    self.log.error(f"API Type: {api_type} thread generated an exception: {exc}", exc_info=True)
                else:
                    self.log.info(f"API Type: {api_type} thread completed")
        return data_to_be_sent

    def get_violations_details(self, violation):
        sess = ClientMixin.get_new_session()
        if "violation_details_url" in violation:
            try:
                fetch_success, result = ClientMixin.make_request(violation["violation_details_url"], method="get",
                                                                 session=sess, logger=self.log,
                                                                 TIMEOUT=self.collection_config['TIMEOUT'],
                                                                 MAX_RETRY=self.collection_config['MAX_RETRY'],
                                                                 BACKOFF_FACTOR=self.collection_config[
                                                                     'BACKOFF_FACTOR'],
                                                                 auth=self.token)
                if fetch_success:
                    return self.transform_violations(result, violation["violation_details_url"])
            except Exception as exc:
                self.log.error("Error Occurred while fetching LogType detailed violation for URL %s",
                               violation["violation_details_url"])

        return []

    def transform_violations(self, violation_object, violation_url):
        data_to_be_sent = []
        if violation_object and "matched_policies" in violation_object:

            issues = self.transform_issue_data(violation_object, violation_url)
            for policy_details in violation_object["matched_policies"]:
                web_hook_format = {"created": self.convert_to_other_time_format(violation_object["created"]),
                                   "watch_name": violation_object["watch_name"],
                                   "policy_name": policy_details["policy"],
                                   "top_severity": violation_object["severity"], "issues": [issues]}

                if web_hook_format:
                    data_to_be_sent.append(web_hook_format)

        return data_to_be_sent

    def transform_issue_data(self, violation_object, violation_url):
        web_hook_issue = {"severity": violation_object["severity"], "type": violation_object["type"],
                          "provider": violation_object["provider"]
                          if "provider" in violation_object else "Unknown",
                          "created": self.convert_to_other_time_format(violation_object["created"]),
                          "description": violation_object[
                              "description"] if "description" in violation_object else violation_object[
                              "issue_id"],
                          "summary": violation_object["summary"]}

        if "properties" in violation_object:
            for CVE in violation_object["properties"]:
                if "cve" in CVE:
                    web_hook_issue["cve"] = CVE["cve"]
                    break

        impacted_artifacts = []
        if "impacted_artifacts" in violation_object:
            for artifact in violation_object["impacted_artifacts"]:
                impacted_artifacts.append(
                    self.transform_artifact_data(violation_url, artifact, violation_object))

            if impacted_artifacts:
                web_hook_issue["impacted_artifacts"] = impacted_artifacts

        return web_hook_issue

    def transform_artifact_data(self, violation_url, artifact_path, violation_object):
        if violation_url is not None:
            comp_id = re.search('comp_id=(.*)&issue_id=', violation_url)
            if comp_id:
                comp_id = comp_id.group(1).replace("%3A", ",").replace("%2F", ",")
                comp_id = re.sub(',+', ',', comp_id)

                values = comp_id.split(",")
                pkg_type = values[0]

                if len(values) == 2:
                    display_name = values[1]
                else:
                    display_name = values[len(values) - 2] + ":" + values[len(values) - 1]

                impacted_artifact = {"display_name": display_name, "path": artifact_path, "pkg_type": pkg_type,
                                     "name": display_name}

                if "infected_components" in violation_object:
                    impacted_components = []
                    for component in violation_object["infected_components"]:
                        impacted_components.append(
                            {"name": re.match(".*://(.*?)$", component).group(1),
                             "path": component, "pkg_type": re.match("(.*?)://", component).group(1)})

                    impacted_artifact["infected_files"] = impacted_components

                if "infected_versions" in violation_object:
                    impacted_artifact["infected_versions"] = violation_object["infected_versions"]

                if "fix_versions" in violation_object:
                    impacted_artifact["fix_versions"] = violation_object["fix_versions"]

                return impacted_artifact
        return []

    def convert_to_other_time_format(self, date):
        epoch = convert_utc_date_to_epoch(date, self.DATE_FORMAT)
        return convert_epoch_to_utc_date(epoch, self.DATE_FORMAT_SUMO_LOGIC_TO_MATCH_WEBHOOK)
