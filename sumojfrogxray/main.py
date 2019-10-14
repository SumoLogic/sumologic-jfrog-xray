import os
import traceback

from sumoappclient.sumoclient.base import BaseCollector

from api import ViolationsLogsAPI


def get_current_dir():
    cur_dir = os.path.dirname(__file__)
    return cur_dir


class SumoJFrogXrayCollector(BaseCollector):
    SINGLE_PROCESS_LOCK_KEY = 'is_jfrog_xray_collector_running'
    CONFIG_FILENAME = "jfrogxraycollector.yaml"

    def __init__(self):
        self.project_dir = get_current_dir()
        super(SumoJFrogXrayCollector, self).__init__(self.project_dir)

        # Set JFrog Xray configuration
        self.api_config = self.config['JFrogXray']

    def is_running(self):
        self.log.debug("Acquiring single instance lock")
        return self.kvstore.acquire_lock(self.SINGLE_PROCESS_LOCK_KEY)

    def stop_running(self):
        self.log.debug("Releasing single instance lock")
        return self.kvstore.release_lock(self.SINGLE_PROCESS_LOCK_KEY)

    def build_task_params(self):
        tasks = [ViolationsLogsAPI(self.kvstore, self.config)]
        return tasks

    def run(self, *args, **kwargs):
        if self.is_running():
            try:
                self.log.info('Starting JFrog Xray Sumo Collector...')
                task_params = self.build_task_params()
                for apiobj in task_params:
                    apiobj.fetch()
            finally:
                self.stop_running()
        else:
            self.kvstore.release_lock_on_expired_key(self.SINGLE_PROCESS_LOCK_KEY, expiry_min=10)


def main(*args, **kwargs):
    try:
        ns = SumoJFrogXrayCollector()
        ns.run()
        # ns.test()
    except BaseException as e:
        traceback.print_exc()


if __name__ == '__main__':
    main()
