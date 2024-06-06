import utils.constant as constant
import pandas as pd
import os
import sys
import utils.alert as alert
import pymssql
import json
import urllib.parse
from sqlalchemy import create_engine,text,engine
from influxdb import InfluxDBClient
from datetime import datetime
import time

class PREPARE:

    def __init__(self,server,database,user_login,password,table,table_columns,table_log,table_columns_log,line_notify_token,influx_server,influx_database,influx_user_login,influx_password,influx_port,mqtt_topic,initial_db,line_notify_flag):
        self.server = server
        self.database = database
        self.user_login = user_login
        self.password = password
        self.table_log = table_log
        self.table = table
        self.table_columns = table_columns
        self.table_columns_log = table_columns_log
        self.df_insert = None
        self.df_influx = None
        self.df_sql = None
        self.line_notify_token = line_notify_token
        self.influx_server = influx_server
        self.influx_database = influx_database
        self.influx_user_login = influx_user_login
        self.influx_password = influx_password
        self.influx_port = influx_port
        self.mqtt_topic = mqtt_topic
        self.initial_db = initial_db
        self.line_notify_flag = line_notify_flag

    def stamp_time(self):
        now = datetime.now()
        print("\nHi this is job run at -- %s"%(now.strftime("%Y-%m-%d %H:%M:%S")))

    def error_msg(self,process,msg,e):
        result = {"status":constant.STATUS_ERROR,"process":process,"message":msg,"error":e}

        try:
            print("Error: "+self.alert_error_msg(result))
            if self.line_notify_flag == "True":
                self.alert_line(self.alert_error_msg(result))
            self.log_to_db(result)
            sys.exit()
        except Exception as e:
            self.info_msg(self.error_msg.__name__,e)
            sys.exit()
    
    def alert_line(self,msg):
        value = alert.line_notify(self.line_notify_token,msg)
        value = json.loads(value)  
        if value["message"] == constant.STATUS_OK:
            self.info_msg(self.alert_line.__name__,'sucessful send to line notify')
        else:
            self.info_msg(self.alert_line.__name__,value)

    def alert_error_msg(self,result):
        if self.line_notify_token != None:
            return f'\nproject: {self.table}\nprocess: {result["process"]}\nmessage: {result["message"]}\nerror: {result["error"]}\n'
                
    def info_msg(self,process,msg):
        result = {"status":constant.STATUS_INFO,"process":process,"message":msg,"error":"-"}
        print(result)

    def ok_msg(self,process):
        result = {"status":constant.STATUS_OK,"process":process,"message":"program running done","error":"-"}
        try:
            self.log_to_db(result)
            print(result)
        except Exception as e:
            self.error_msg(self.ok_msg.__name__,'cannot ok msg to log',e)
    
    def conn_sql(self):
        #connect to db
        try:
            cnxn = pymssql.connect(self.server, self.user_login, self.password, self.database)
            cursor = cnxn.cursor()
            return cnxn,cursor
        except Exception as e:
            self.alert_line("Danger! cannot connect sql server")
            self.info_msg(self.conn_sql.__name__,e)
            sys.exit()

    def log_to_db(self,result):
        #connect to db
        cnxn,cursor=self.conn_sql()
        try:
            cursor.execute(f"""
                INSERT INTO [{self.database}].[dbo].[{self.table_log}] 
                values(
                    getdate(), 
                    '{result["status"]}', 
                    '{result["process"]}', 
                    '{result["message"]}', 
                    '{str(result["error"]).replace("'",'"')}'
                    )
                    """
                )
            cnxn.commit()
            cursor.close()
        except Exception as e:
            self.alert_line("Danger! cannot insert log table")
            self.info_msg(self.log_to_db.__name__,e)
            sys.exit()


class ALARMLIST(PREPARE):

    def __init__(self,server,database,user_login,password,table,table_columns,table_log,table_columns_log,influx_server,influx_database,influx_user_login,influx_password,influx_port,mqtt_topic,initial_db,line_notify_flag,line_notify_token=None):
        super().__init__(server,database,user_login,password,table,table_columns,table_log,table_columns_log,line_notify_token,influx_server,influx_database,influx_user_login,influx_password,influx_port,mqtt_topic,initial_db,line_notify_flag)      
    
    def query_influx(self) :
        try:
            result_lists = []
            client = InfluxDBClient(self.influx_server, self.influx_port, self.influx_user_login,self.influx_password, self.influx_database)
            mqtt_topic_value = list(str(self.mqtt_topic).split(","))
            for i in range(len(mqtt_topic_value)):
                query = f"select time,status,topic from mqtt_consumer where topic ='{mqtt_topic_value[i]}' order by time desc limit 100"
                result = client.query(query)
                result_df = pd.DataFrame(result.get_points())
                result_lists.append(result_df)
            query_influx = pd.concat(result_lists, ignore_index=True)
            if not query_influx.empty :
                self.df_influx = query_influx
            else:
                self.df_influx = None
                self.info_msg(self.query_influx.__name__,"influxdb data is emply")
        except Exception as e:
            self.error_msg(self.query_influx.__name__,"cannot query influxdb",e)

    def edit_col(self):
            try:
                df = self.df_influx.copy()
                df_split = df['topic'].str.split('/', expand=True)
                df['mc_no'] = df_split[3].values
                df['process'] = df_split[2].values
                df.drop(columns=['topic'],inplace=True)
                df.rename(columns = {'time':'occurred'}, inplace = True)
                df["occurred"] =   pd.to_datetime(df["occurred"]).dt.tz_convert(None)
                df["occurred"] = df["occurred"] + pd.DateOffset(hours=7)    
                df["occurred"] = df['occurred'].apply(lambda x: x.strftime('%Y-%m-%d %H:%M:%S'))
                df.rename(columns={'status': 'alarm'}, inplace=True)
                self.df_influx = df
            except Exception as e:
                self.error_msg(self.edit_col.__name__,"cannot edit dataframe data",e)

    def query_sql(self):
        try:
            encoded_password = urllib.parse.quote_plus(self.password)
            engine1 = create_engine(f'mssql+pymssql://{self.user_login}:{encoded_password}@{self.server}/{self.database}')
            sql_query = f"""SELECT TOP 2000 * FROM [{self.database}].[dbo].[{self.table}] ORDER by occurred desc"""
            df_sql = pd.read_sql(sql_query, engine1)
            columns = df_sql.columns.tolist()
            new_order = [columns[0], columns[2], columns[3],columns[4], columns[1]]
            self.df_sql = df_sql[new_order]

            if self.df_sql.empty :
                self.info_msg(self.query_sql.__name__,f"data is emply")
            return self.df_sql
        except Exception as e:
                self.error_msg(self.query_sql.__name__,"cannot select with sql code",e)
 
    def check_duplicate(self):
        try:
            df_from_influx = self.df_influx
            df_from_sql = self.df_sql       
            df_from_influx['occurred'] = pd.to_datetime(df_from_influx['occurred'])
            df_from_sql['occurred'] = pd.to_datetime(df_from_sql['occurred'])
            merged_df = df_from_influx.merge(df_from_sql,on=["occurred","mc_no","alarm","process"],how= 'left',indicator = True)
            df_not_duplicate = merged_df[merged_df['_merge'] == 'left_only'].drop(columns=['registered_at', '_merge'])
            if df_not_duplicate.empty:    
                self.df_insert=None     
                self.info_msg(self.check_duplicate.__name__,f"data is not new for update")
            else:
                self.info_msg(self.check_duplicate.__name__,f"we have data new")
                self.df_insert = df_not_duplicate       

                return constant.STATUS_OK   
        except Exception as e:
            self.error_msg(self.check_duplicate.__name__,"cannot select with sql code",e)
    
    def df_to_db(self):
        #connect to db
        alarm_list = ['occurred','alarm','mc_no','process']
        cnxn,cursor=self.conn_sql()
        try:
            if not self.df_insert.empty:  
                df = self.df_insert
                for index, row in df.iterrows():
                    value = None
                    for i in range(len(alarm_list)):
                        address = alarm_list[i]
                        if value == None:
                            value = ",'"+str(row[address])+"'"
                        else:
                            value = value+",'"+str(row[address])+"'"
                    insert_string = f"""
                    INSERT INTO [{self.database}].[dbo].[{self.table}] 
                    values(
                        getdate()
                        {value}
                        )
                        """
                    cursor.execute(insert_string)
                    cnxn.commit()
                cursor.close()
                self.df_insert = None

                self.info_msg(self.df_to_db.__name__,f"insert data successfully")     
        except Exception as e:
            print('error: '+str(e))
            self.error_msg(self.df_to_db.__name__,"cannot insert df to sql",e)

    def run(self):
        self.stamp_time()
        if self.initial_db == 'True':
            self.query_influx()
            if self.df_influx is not None:
                self.edit_col()
                self.query_sql()
                if self.df_sql is None:
                    self.df_insert = self.df_influx
                    time.sleep(5)
                    self.df_to_db()
                    self.ok_msg(self.df_to_db.__name__)
                else:
                    self.check_duplicate()
                    if self.df_insert is not None:
                        time.sleep(5)
                        self.df_to_db()
                        self.ok_msg(self.df_to_db.__name__)
        else:
            print("db is not initial yet")
if __name__ == "__main__":
    print("must be run with main")
