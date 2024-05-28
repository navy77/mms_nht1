import utils.constant as constant
import pandas as pd
import os
import sys
import utils.alert as alert
import pymssql
import json
import datetime
# from datetime import datetime,date, timedelta
from sqlalchemy import create_engine,text,engine
from influxdb import InfluxDBClient
import time

class PREPARE:

    def __init__(self,server,database,user_login,password,table,table_columns,table_log,table_columns_log,line_notify_token,influx_server,influx_database,influx_user_login,influx_password,influx_port,column_names,mqtt_topic,initial_db,calculate_function,line_notify_flag):
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
        self.column_names = column_names
        self.mqtt_topic = mqtt_topic
        self.initial_db = initial_db
        self.line_notify_flag = line_notify_flag
        self.calculate_function = calculate_function

    def stamp_time(self):
        now = datetime.datetime.now()
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
 
class INFLUX_TO_SQLSERVER(PREPARE):
    def __init__(self,server,database,user_login,password,table,table_columns,table_log,table_columns_log,influx_server,influx_database,influx_user_login,influx_password,influx_port,column_names,mqtt_topic,initial_db,calculate_function,line_notify_flag,line_notify_token=None):
        super().__init__(server,database,user_login,password,table,table_columns,table_log,table_columns_log,line_notify_token,influx_server,influx_database,influx_user_login,influx_password,influx_port,column_names,mqtt_topic,initial_db,calculate_function,line_notify_flag)        

    def calculate1(self) :
        try:
            result_lists = []
            client = InfluxDBClient(self.influx_server, self.influx_port, self.influx_user_login,self.influx_password, self.influx_database)
            mqtt_topic_value = list(str(self.mqtt_topic).split(","))
        
            for i in range(len(mqtt_topic_value)):
                query = f"select time,topic,model,spec,d_str1,d_str2,{self.column_names} from mqtt_consumer where topic = '{mqtt_topic_value[i]}' order by time desc limit 1"
                result = client.query(query)
                if list(result):
                    result = list(result)[0][0]
                    result_lists.append(result)
                    result_df = pd.DataFrame.from_dict(result_lists)
            self.df_influx = result_df

        except Exception as e:
            self.error_msg(self.calculate1.__name__,"cannot query influxdb",e)
      
    def calculate2(self) :
        try:
            # columns_to_sum = ['ball_c1_ok','ball_c2_ok','ball_c3_ok','ball_c4_ok','ball_c5_ok','ball_c1_ng','ball_c2_ng','ball_c3_ng','ball_c4_ng','ball_c5_ng']
            # columns_not_sum = ['time', 'topic', 'd_str1', 'd_str2','rssi','ball_c1_remain','ball_c2_remain','ball_c3_remain','ball_c4_remain','ball_c5_remain',
            #                    'ball_gauge_c1','ball_gauge_c2','ball_gauge_c3','ball_gauge_c4','ball_gauge_c5','rtnr_ok','rtnr_ng','ball_sepa_ng','ball_shot_ng',
            #                    'production_daily_ok','production_daily_ng','average_cycle_time','ball_use_brg']
            columns_to_sum = ['daily_ok','daily_ng','daily_tt','c1_ok','c2_ok','c3_ok','c4_ok','c5_ok','c1_ng','c2_ng','c3_ng','c4_ng','c5_ng',
                              'cycle_t','target_u','error_t','alarm_t','run_t','stop_t','wait_p_t','full_p_t','adjust_t','set_up_t','plan_s_t','time_hr','time_min']
            columns_not_sum = ['time', 'topic', 'spec','d_str1', 'd_str2','rssi']
            client = InfluxDBClient(self.influx_server, self.influx_port, self.influx_user_login,self.influx_password, self.influx_database)
            mqtt_topic_value = list(str(self.mqtt_topic).split(","))

            now = datetime.datetime.now()
            current_time_epoch = int(time.time()) * 1000 *1000 *1000
            one_hour_ago = now - datetime.timedelta(hours=1)
            previous_time_epoch = int(one_hour_ago.timestamp()) * 1000 *1000 *1000
            df_data = pd.DataFrame(columns=['time'] + columns_to_sum)

            for i in range(len(mqtt_topic_value)):
                query = f"select time,topic,model,spec,d_str1,d_str2,{self.column_names} from mqtt_consumer where topic = '{mqtt_topic_value[i]}' and time >= {previous_time_epoch} and time < {current_time_epoch} " 
                result = client.query(query)
                df_result = pd.DataFrame(result.get_points())
                if not df_result.empty:
                    df_result = df_result.sort_values(by='time',ascending=False)
                    df_result = df_result.fillna(0)
                    df_result = df_result[df_result['model'] != '0']
                    df_result['judge'] = df_result.groupby('model')['daily_ok'].diff().fillna(0) > 0
                    df1 = df_result.groupby('model').head(1)
                    df2 = df_result[df_result['judge']]
 
                    for model_value in df1['model'].unique():
                        df1_filtered = df1[df1['model'] == model_value]
                        df2_filtered = df2[df2['model'] == model_value]

                        for col in columns_to_sum:
                            sum_value = df1_filtered[col].iloc[0] + df2_filtered[col].sum()
                            df_data.loc[model_value, col] = sum_value

                        for col in columns_not_sum:
                            df_data.loc[model_value, col] = df1_filtered[col].iloc[0]

                        df_data.loc[model_value, 'model'] = model_value

            self.df_influx = df_data
            print(self.df_influx)
        except Exception as e:  
            self.error_msg(self.calculate2.__name__,"cannot query influxdb",e)

    def edit_col(self):
        try:
            df = self.df_influx.copy()
            df_split = df['topic'].str.split('/', expand=True)
            df['mc_no'] = df_split[3].values
            df['process'] = df_split[2].values
            df.drop(columns=['topic'],inplace=True)
            df.rename(columns = {'time':'data_timestamp'}, inplace = True)
            df["data_timestamp"] =   pd.to_datetime(df["data_timestamp"]).dt.tz_convert(None)
            df["data_timestamp"] = df["data_timestamp"] + pd.DateOffset(hours=7)    
            df["data_timestamp"] = df['data_timestamp'].apply(lambda x: x.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])
            df.fillna(0,inplace=True)
            self.df_insert = df

        except Exception as e:
            self.error_msg(self.edit_col.__name__,"cannot edit dataframe data",e)

    def df_to_db(self):
        #connect to db
        init_list = ['mc_no','process','model','spec','d_str1','d_str2']
        insert_db_value = self.column_names.split(",")
        col_list = init_list+insert_db_value
        cnxn,cursor=self.conn_sql()
        try:
            df = self.df_insert
            for index, row in df.iterrows():
                value = None
                for i in range(len(col_list)):
                    address = col_list[i]
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
            if self.calculate_function == '1':
                self.calculate1()
            elif self.calculate_function == '2':
                self.calculate2()   
            else :self.calculate1()

            if not self.df_influx.empty:
                self.edit_col()
                self.df_to_db()
                self.ok_msg(self.df_to_db.__name__)
        else:
            print("db is not initial yet")
if __name__ == "__main__":
    print("must be run with main")
