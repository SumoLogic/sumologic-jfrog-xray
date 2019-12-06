# sumologic-jfrog-xray

Solution to pull logs from JFrog Xray to Sumo Logic


## Installation

This collector can be deployed both onprem and on cloud.


### Deploying the collector on a VM
1. Get details for your JFrog Xray instance. 
    - Get Host Name and port for your JFrog Xray instance.
        - For eg - URL is http://host-example:8000/web/#/login.
          * Host Name = host-example
          * port = 8000
    * UserName and password for your JFrog Xray instance.
    
2. Add a Hosted Collector and one HTTP Logs Source

    * To create a new Sumo Logic Hosted Collector, perform the steps in [Configure a Hosted Collector](https://help.sumologic.com/03Send-Data/Hosted-Collectors/Configure-a-Hosted-Collector).
    * Add an [HTTP Logs and Metrics Source](https://help.sumologic.com/03Send-Data/Sources/02Sources-for-Hosted-Collectors/HTTP-Source).

3. Using the **sumologic-jfrog-xrayy** collector 
    * **Method 1** - Configuring the **sumologic-jfrog-xray** collector

        Below instructions assume pip is already installed if not then, see the pip [docs](https://pip.pypa.io/en/stable/installing/) on how to download and install pip.
    *sumologic-jfrog-xray* is compatible with python 3.7 and python 2.7. It has been tested on Ubuntu 18.04 LTS and Debian 4.9.130.
    Login to a Linux machine and download and follow the below steps:

        * Install the collector using below command
      ``` pip install sumologic-jfrog-xray```

        * Create a configuration file named jfrogxraycollector.yaml in home directory by copying the below snippet.

            ```
            JFrogXray:
                HOSTNAME: "<Paste the Host of JFrog Xray Instance>"
                PORT: <Paste the Port of JFrog Xray Instance>
                USERNAME: <Paste the UserName of JFrog Xray Instance>
                PASSWORD: <Paste the password of JFrog Xray Instance>
                
            SumoLogic:
                HTTP_LOGS_ENDPOINT: <Paste the URL for the HTTP Logs source from step 2.>
             
            Collection:
                BACKFILL_DAYS: <Enter the Number of days before the event collection will start.>
            ```
    * Create a cron job  for running the collector every 5 minutes by using the crontab -e and adding the below line

        `*/5 * * * *  /usr/bin/python -m sumojfrogxray.main > /dev/null 2>&1`

   * **Method 2** - Collection via an AWS Lambda function
   
        To install Sumo Logic’s AWS Lambda script, follow the instructions below:

        * Go to https://serverlessrepo.aws.amazon.com/applications
        * Search for “sumologic-jfrog-xray” and select the app as shown below:
        ![App](https://appdev-readme-resources.s3.amazonaws.com/JFrog+Xray/App.png)

        * In the Configure application parameters panel, shown below:
        ![Deploy](https://appdev-readme-resources.s3.amazonaws.com/JFrog+Xray/Deploy.png)

            ```
            Hostname: Paste the Host of JFrog Xray Instance from step 1.
            HttpLogsEndpoint: Paste the URL for the HTTP Logs source from step 2.
            Password: Paste the password of JFrog Xray Instance from step 1.
            Port: Paste the Port of JFrog Xray Instance from step 1.
            Usernname: Paste the UserName of JFrog Xray Instance from step 1.
            BackfillDays: Enter the Number of days before the event collection will start
            ```
        * Click Deploy.

