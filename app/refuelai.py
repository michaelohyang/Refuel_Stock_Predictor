# -*- coding: utf-8 -*-
"""RefuelAi.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1HcdSsSaj4H_K33oFje9ILw_8f2-gkI8p
"""

!pip install evadb
!pip install -q streamlit
!npm install localtunnel
!apt -qq install postgresql
!service postgresql start
!pip install sqlalchemy
!pip install 'refuel-autolabel[openai]'

!wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
!chmod +x cloudflared-linux-amd64
# import subprocess
# subprocess.Popen(["./cloudflared-linux-amd64", "tunnel", "--url", "http://localhost:8501"])
!nohup /content/cloudflared-linux-amd64 tunnel --url http://localhost:8501 &

!sudo -u postgres psql -c "CREATE USER eva WITH SUPERUSER PASSWORD 'password'"
!sudo -u postgres psql -c "CREATE DATABASE evadb"

import warnings
warnings.filterwarnings("ignore")

from IPython.core.display import display, HTML
def pretty_print(df):
    return display(HTML( df.to_html().replace("\\n","<br>")))

import evadb
cursor = evadb.connect().cursor()

params = {
    "user": "eva",
    "password": "password",
    "host": "localhost",
    "port": "5432",
    "database": "evadb",
}
query = f"CREATE DATABASE postgres_data WITH ENGINE = 'postgres', PARAMETERS = {params};"
cursor.query(query).df()

# %%writefile app.py

import streamlit as st
from plotly import graph_objs as go
import pandas as pd
import os
from sqlalchemy import create_engine

START = "2007-11-25"
STOP = "2021-04-30"

st.title("_Stock.ai_ :sunglasses:")

data_file = st.file_uploader("Stock Market Data", ["csv"], help="Please upload a 1 csv file at a time", )
df = None

# If a file is uploaded, read it into a DataFrame
if data_file is not None:
    df = pd.read_csv(data_file, usecols=list(range(10)))

    # Display the DataFrame
    st.dataframe(df)

    cursor.query("""
      USE postgres_data {
        CREATE TABLE IF NOT EXISTS finance_data (
            Date VARCHAR(64),
            Symbol VARCHAR(64),
            Series VARCHAR(64),
            Prev_Close INT,
            Open INT,
            High INT,
            Low INT,
            Last INT,
            Close INT,
            VWAP INT
        )
      }
    """).df()

    engine = create_engine('postgresql://eva:password@localhost:5432/evadb')
    # Replace 'finance_data' with your actual table name
    table_name = 'finance_data'

    # Use the to_sql method to write the DataFrame to the PostgreSQL table
    df.to_sql(table_name, con=engine, if_exists='replace', index=False)

    engine.dispose()

    cursor.query("SELECT * FROM postgres_data.finance_data LIMIT 3;").df()

import os

# provide your own OpenAI API key here
os.environ['OPENAI_API_KEY'] = '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'

refuel_config = {
    "task_name": "FinancialChatbot",
    "task_type": "chat",
    "dataset": {
        "label_column": "response",
        "delimiter": ","
    },
    "model": {
        "provider": "openai",
        "name": "gpt-3.5-turbo",
        "params": {}
    },
    "prompt": {
        "task_guidelines": "You are a financial consultant. Provide responses based on the given context.",
        "few_shot_examples": [
            {
                "context": "The stock market has been volatile recently due to economic uncertainties.",
                "response": "It's common for the stock market to experience volatility during uncertain times. Diversifying your portfolio can help manage risks."
            },
            {
                "context": "I'm thinking of investing in technology stocks. What are your recommendations?",
                "response": "Investing in technology stocks can offer growth potential. Consider companies with strong fundamentals and a track record of innovation."
            },
            {
                "context": "What are the key factors to consider when analyzing a company's financial statements?",
                "response": "When analyzing financial statements, look at key indicators like revenue growth, profit margins, and debt levels. It's crucial to understand a company's financial health."
            }
        ],
        "few_shot_selection": "fixed",
        "few_shot_num": 3,
        "example_template": "Context: {context}\nResponse: {response}"
    }
}

# %%writefile autolabelrefuel.py

import pandas as pd
import os
import json

from evadb.catalog.catalog_type import NdArrayType
from evadb.functions.abstract.abstract_function import AbstractFunction
from evadb.functions.decorators.decorators import forward, setup
from evadb.functions.decorators.io_descriptors.data_types import PandasDataframe

from autolabel import LabelingAgent, AutolabelDataset

class AutoLabelRefuel(AbstractFunction):

    @setup(cacheable=False, function_type="FeatureExtraction", batchable=False)
    def setup(self, config=None):
        if config:
            self.config = config
        else:
            self.config = refuel_config

    @property
    def name(self) -> str:
        return "AutoLabelRefuel"

    @forward(
        input_signatures=[
            PandasDataframe(
                columns=["data"],
                column_types=[NdArrayType.STR],
                column_shapes=[(None, 5)],
            ),
        ],
        output_signatures=[
            PandasDataframe(
                columns=["response"],
                column_types=[NdArrayType.STR],
                column_shapes=[(None,)],
            )
        ],
    )
    def forward(self, df: pd.DataFrame) -> pd.DataFrame:
        task = df.iloc[0,0]
        df.drop([0,0], axis=1, inplace=True)

        agent = LabelingAgent(config=self.config)
        if task=="run":
            response = agent.run(df)

        elif task=="plan":
            response = agent.plan(df)

        df_dic = {"response": [str(response)]}

        result = pd.DataFrame(df_dic)
        return pd.DataFrame(result)

create_function_query = f"""CREATE FUNCTION IF NOT EXISTS AutoLabelRefuel
      IMPL  'autolabelrefuel.py';
      """

cursor.query("DROP FUNCTION IF EXISTS AutoLabelRefuel;").execute()
cursor.query(create_function_query).execute()

print("Function Created Successfully")

query= f""" SELECT AutoLabelRefuel("run", Date, Symbol, Series, Prev_Close, Open, High, Low, Last, Close, VWAP) FROM finance_data;"""
result = cursor.query(query).execute()


chatbot = st.text_input('', 'Ask me about the stock')

!grep -o 'https://.*\.trycloudflare.com' nohup.out | head -n 1 | xargs -I {} echo "Your tunnel url {}"
!streamlit run /content/app.py &>/content/logs.txt &