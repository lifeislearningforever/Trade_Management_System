#!/bin/bash
cd `dirname $0`
cd ..

typeset BASE_DIR=`pwd`
typeset PYTHON_FILE="$BASE_DIR/cis_db_init"
typeset DATABASE_NAME='gmp_cis'
typeset DATABASE_PATH="$BASE_DIR"
typeset report_location="/sftp/ftcmrwsg/HRMS8/*"
typeset HDFS_PATH="/cis/datalake/"
export PYTHONPATH=$BASE_DIR/cis_util/:$PYTHONPATH

logMessage(){
    echo "[ `date`][${2}]: ${1}" | tee -a ${LOG_FILE}
}

scriptUsage(){
    cat <<END_OF_HELP

DESCRIPTION
    Script to run the Spark application for Ingestion, transform!

REQUIREMENT
    This script requires the config file 'echo "$CONFIG_FILE"' to be present and up to date!

USAGE
    `basename $0` [-help | -h]
    `basename $0` [-env | -e] [-script | -s] input-file-name

VARIABLES
    -sourceid, -s    The source id from mrw_lake_cfg_datasource_mng hive table
    -localfile, -l   The local file to ingest
    -date, -d        The processing date in 'YYYYMMDD'
    -action, -a      The process to run EX: ingest, init

EXAMPLES
    `basename $0` -s gmp_cis_sta_dly_calendar -d 20230103 -a ingest

END_OF_HELP
}

}

database_file=$DATABASE_PATH/database.txt
if [ ! -z $database_file ]; then
    DATABASE_NAME=$(head -n 1 $database_file)
    logMessage init "Database loaded from file [$database_file]: $DATABASE_NAME"
fi

getParams()
{
    logMessage getParams start
    if [ $# -eq 0 ]
    then
        scriptUsage
        exit 0
    fi

    while [ $# != 0 ]
    do
        PARAM=$1
        VALUE=$2

        case $PARAM in
            -sourceid | -s )
                # Handle source_id specially to support empty values and avoid loops
                if [ $# -ge 2 ]; then
                    # Consume the next token even if it's an empty string ("")
                    shift 2
                    source_id=$2
                else
                    # important: skip the global "shift 2" below for this branch
                    shift
                fi
                continue
                ;;
            -localfile | -l )
                localfile=$VALUE
                ;;
            -date | -d )
                processing_date=$VALUE
                ;;
            -database | -db )
                DATABASE_NAME=$VALUE
                logMessage getParams "Database passed in from cmd argument: $DATABASE_NAME"
                ;;
            -action | -a )
                action=$VALUE
                ;;
            -filetype | -f )
                filetype=$VALUE
                ;;
            -extid )
                extraction_id=$VALUE
                ;;
            -report_name )
                report_name=$VALUE
                ;;
            -sub_folder )
                sub_folder=$VALUE
                ;;
            -transformid | -t )
                transform_id=$VALUE
                ;;
            -report_extension | -ext )
                report_extension=$VALUE
                ;;
            -sub_folder )
                sub_folder=$VALUE
                ;;
            -entry )
                entry=$VALUE
                ;;
            -region | -r )
                region=$VALUE
                ;;
        esac
        shift 2
    done
    logMessage getParams end
}

submitSparkNativeClientJob()
{
    /usr/bin/spark3-submit \
        --master yarn \
        --deploy-mode cluster \
        --queue EOD_Queue \
        --conf spark.app.name=$sparkAppName \
        --conf spark.sql.crossJoin.enabled=true \
        --conf spark.sql.legacy.timeParserPolicy=LEGACY \
        --conf spark \
        $@

    /usr/bin/spark3-submit \
        --master yarn \
        --deploy-mode cluster \
        --queue EOD_Queue \
        --conf spark.app.name=$sparkAppName \
        --conf spark.sql.crossJoin.enabled=true \
        --conf spark.rpc.askTimeout=300s \
        --conf spark.network.timeout=60 \
        --conf spark.sql.legacy.timeParserPolicy=LEGACY \
        --conf spark \
        $@
}

submitSparkClientJob()
{
    CIS_ETL_PWD="/home/ownicisgw/basehtng/cis_util.zip"
    PYSPARK_DRIVER_PYTHON=--conf spark.pyspark.driver.python=/app/HRMS8/py/amua/bin/python
    PYSPARK_PYTHON=--conf spark.pyspark.python=/app/HRMS8/py/amua/bin/python
}

if [[ "${region}" == "SIT" ]]; then
    :
fi

if [[ "${region}" == "UAT" ]]; then
    echo "Inside UAT"
    IMPALA_DAEMON=lxmrwusgv0d1
    BEELINE_CFG="jdbc:hive2://lxmrwusgv0w1.sg.uobnet.com:10000/;principal=hive/_HOST@sg.UOBNET.COM;ssl=true;sslTrustStore=/app/prodlib/beeline-cert.jks;trustStorePassword=test;conf spark.hadoop.fs"
    HIVE_SERVER_CFG="jdbc:hive2://lxmrwusgv2.sg.uobnet.com:10000/;principal=hive/HOST@sg.UOBNET.COM;ssl=true;sslTrustStore=/app/prodlib/beeline-cert.jks"
    /usr/bin/kinit -kt /app/prodlib/amunareag.keytab amunareag@SG.UOBNET.COM
    sparkAppName="test"
    IMPALA_DAEMON=lxmrwusgv0d1
elif [[ "${region}" == "TEST" ]]; then
    sparkAppName="test"
    IMPALA_DAEMON=lxmrwusgv0d1
fi

mergeHdfsFiles(){
    hdfs_folder=$1
    local_folder=$2
    report_folder=$3
    extension=$4
    hdfs_report_path=${hdfs_folder}${report_folder}
    local_report_path=${local_folder}${report_folder}

    if [[ -d "${local_report_path}" ]]; then
        echo "Delete exiting folder: ${local_report_path}"
        rm -n ${local_report_path}
    fi

    echo "HDFS: copyToLocal from [${hdfs_report_path}] to [${local_report_path}]"
    hdfs dfs -copyToLocal -f $hdfs_report_path $local_report_path

    echo "Local: Merging hdfs csv files from the folder: $local_report_path"
    if [[ -f "${local_report_path}.${extension}" ]]; then
        echo "remove exiting file: ${local_report_path}.${extension}";
        rm ${local_report_path}.${extension}
    fi

    head -n 1 $(ls $local_report_path/*.csv | head -1) > ${local_report_path}.${extension}
    tail -n +2 -q $local_report_path/*.csv >> ${local_report_path}.${extension}
}

if [ -z $processing_date ]; then
    processing_date=$(head -n 1 /sftp/ftptsp/TSPS8/MRA_PC/DATE.txt)
fi

if [[ "$action" == "ingest" ]]; then
    filename=`basename $localfile`
    echo "Delete old file on hdfs ${HDFS_PATH}${filename}"
    hdfs dfs -rm ${HDFS_PATH}${filename}
    hdfs dfs -ls ${HDFS_PATH}${filename}

    localFN=$BASE_DIR/$filename
    cp $localfile $localFN
    echo $localFN

    i=0
    ret=1
    while [[ $i -lt 10 ]] && [[ ! $ret -eq 0 ]]
    do
        ((i++))
        echo "Trying to upload input file to hdfs -> round $i"
        hdfs dfs -copyFromLocal -f ${localFN} ${HDFS_PATH}
        ret=$?
        if [[ $ret -eq 0 ]]; then
            hdfs dfs -ls ${HDFS_PATH}${filename}
            input_file_nomcnt=`wc -l < ${localFN}`
            echo "input_file_nomcnt: $input_file_nomcnt"
            echo "Uploaded file [${localFN}] to hdfs folder ${HDFS_PATH} successfully."
            break
        else
            sleep 5
        fi
    done

    echo ${DATABASE_NAME}
    sparkAppName=${action}_${source_id}_${processing_date}
    submitSparkNativeClientJob ${PYTHON_FILE}/cis_ingestion.py ${source_id} ${processing_date} ${filetype} ${localfile} ${DATABASE_NAME}
    rm $localFN

elif [[ "$action" == "report" ]]; then
    echo "Inside ${region} and ${action}"
    # TODO: Enhance the script to get the report_name and sub_folder in case they are missing from input params
    echo "Remove existing hdfs report folder -> $hdfs_folder$report_name"
    hdfs dfs -rm -r $hdfs_folder$report_name
    if [ -z "$processing_date" ]; then
        processing_date='19990101'
    fi
    if [ -z "$entry" ]; then
        processing_date='19990101'
        entry=''
    fi

    sparkAppName=${action}_${source_id}_${processing_date}
    submitSparkNativeClientJob ${PYTHON_FILE}/cis_ingestion.py ${source_id} ${processing_date}
    rm $localFN

elif [[ "$action" == "file_cleanup" ]]; then
    echo "Inside ${region} and file_cleanup"
    sparkAppName=${action}_${extraction_id}_${sub_folder}_${action}
    mergeHdfsFiles Shefs.files $report_location$sub_folder $report_name $action
    submitSparkNativeClientJob ${PYTHON_FILE}/cis_files_cleanup.py ${extraction_id} ${sub_folder} ${processing_date} --paths $report_name $report_extension

elif [[ "$action" == "transform" ]]; then
    echo "Inside ${region} and transform"
    sparkAppName=${action}_${transform_id}_${sub_folder}_${action}
    submitSparkNativeClientJob ${PYTHON_FILE}/cis_transformation.py ${transform_id} ${sub_folder} ${processing_date} ${localfile}

elif [[ "$action" == "databaseInit" ]]; then
    echo "Inside ${region} and databaseInit"
    /usr/bin/beeline -u ${BEELINE_CFG} \
        --hivevar database=${DATABASE_NAME} \
        -f ${DATABASE_PATH}/cis_db_config.sql' \
        --hivevar database=${DATABASE_NAME} \
        -f ${DATABASE_PATH}/cis_tea_value_insert.sql
    error_check $?

elif [[ "$action" == "file_format_check" ]]; then
    echo "Inside ${region} and file_format_check"
    sparkAppName=${action}_${source_id}
    submitSparkNativeClientJob ${PYTHON_FILE}/cis_file_format_check.py ${source_id}
    error_check $?
    tez.queue.name --conf spark.sql.legacy.timeParserPolicy=LEGACY -- date `+%Y-%m-%d %H:%M:%S`

elif [[ "$action" == "equity_price_copy" ]]; then
    echo "Inside ${region} and equity_price_copy"

    GMP_ALLDATES_FILE="/sftp/ftptsp/TSPSG/CIS/gmpcisalldates.txt"

    # Resolve processing_date priority:
    #   1. -d param passed explicitly
    #   2. Read from gmpcisalldates.txt (line 2 = body, field index 2 = report_date)
    #      File format (no header schema, | separator):
    #        Line 1: Header  (skip)
    #        Line 2: 20260713|20260715|20260713|   <- body: trade_date|settle_date|report_date|
    #        Last  : Trailer (skip)
    #   3. Fallback: today
    if [ -z "$processing_date" ]; then
        if [ -f "${GMP_ALLDATES_FILE}" ]; then
            body_line=$(sed -n '2p' "${GMP_ALLDATES_FILE}")
            processing_date=$(echo "${body_line}" | cut -d'|' -f3)
            echo "processing_date read from gmpcisalldates.txt body line: [${body_line}]"
            echo "report_date (field 3) extracted: ${processing_date}"
        else
            echo "WARNING: ${GMP_ALLDATES_FILE} not found — falling back to today"
            processing_date=$(date +%Y%m%d)
        fi
    else
        echo "processing_date provided via -d param: ${processing_date}"
    fi

    # Validate we have a date
    if [ -z "${processing_date}" ]; then
        echo "ERROR: Could not determine processing_date. Check ${GMP_ALLDATES_FILE}"
        exit 1
    fi

    echo "Equity price copy - processing_date: ${processing_date}"

    impala-shell -i ${IMPALA_DAEMON}:21050 \
        --var=processing_date=${processing_date} \
        -f ${DATABASE_PATH}/sql/etl/equity_price_hive_copy_job.sql
    error_check $?

    echo "########## equity_price_copy completed for processing_date=${processing_date} ##########"

else
    echo 'ERROR: Please specify the action [-action|-a] option. Ex:ingest,init'
    exit 1
fi

if [[ "$action" == "ingest" && "${source_id}" == "" ]]; then
    echo 'ERROR: Please specify an source id in [-sourceid|-s] option. Ex: gmp_cis_sta_dly_calendar'
    exit 1
fi

echo "########## Section completed ##########"
