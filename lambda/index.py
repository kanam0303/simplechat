import json
import os
import boto3
import re  # 正規表現モジュールをインポート
from botocore.exceptions import ClientError
import urllib.request  # 標準ライブラリのurllib.requestを使用
from urllib.error import URLError, HTTPError

# グローバル変数の初期化
bedrock_client = None

# Lambda コンテキストからリージョンを抽出する関数
def extract_region_from_arn(arn):
    # ARN 形式: arn:aws:lambda:region:account-id:function:function-name
    match = re.search('arn:aws:lambda:([^:]+):', arn)
    if match:
        return match.group(1)
    return "us-east-1"  # デフォルト値

# FastAPIへのHTTPリクエスト
API_ENDPOINT = os.environ.get("API_ENDPOINT", "https://a1ae-34-124-132-250.ngrok-free.app/generate")

def lambda_handler(event, context):
    try:
        # コンテキストから実行リージョンを取得し、クライアントを初期化
        global bedrock_client
        if bedrock_client is None:
            region = extract_region_from_arn(context.invoked_function_arn)
            bedrock_client = boto3.client('bedrock-runtime', region_name=region)
            print(f"Initialized Bedrock client in region: {region}")
        
        print("Received event:", json.dumps(event))
        
        # Cognitoで認証されたユーザー情報を取得
        user_info = None
        if 'requestContext' in event and 'authorizer' in event['requestContext']:
            user_info = event['requestContext']['authorizer']['claims']
            print(f"Authenticated user: {user_info.get('email') or user_info.get('cognito:username')}")
        
        # リクエストボディの解析
        body = json.loads(event['body'])
        message = body['message']
        conversation_history = body.get('conversationHistory', [])
        
        print("Processing message:", message)
        print("Using API endpoint:", API_ENDPOINT)
        
        # 会話履歴を使用
        messages = conversation_history.copy()
        
        # ユーザーメッセージを追加
        messages.append({
            "role": "user",
            "content": message
        })
        
        # FastAPI用のリクエストペイロードを構築
        # シンプルな実装として、メッセージのみを送信
        request_data = {
            "prompt": message,
            "max_new_tokens": 512,
            "temperature": 0.7,
            "top_p": 0.9,
            "do_sample": True
        }
        
        # HTTPリクエスト用のヘッダー
        headers = {
            'Content-Type': 'application/json'
        }
        
        # JSONデータをUTF-8でエンコード
        data = json.dumps(request_data).encode('utf-8')
        
        print("Calling FastAPI with payload:", json.dumps(request_data))
        
        # HTTPリクエストオブジェクトを作成
        req = urllib.request.Request(API_ENDPOINT, data=data, headers=headers, method='POST')
        
        # APIリクエストを送信して応答を取得 - タイムアウト設定を追加 (30秒)
        with urllib.request.urlopen(req, timeout=30) as response:
            response_data = response.read()
            response_body = json.loads(response_data.decode('utf-8'))
        
        print("API response:", json.dumps(response_body, default=str))

        # 応答からテキストを取得（FastAPIのレスポンス形式に合わせる）
        # FastAPIでは、{"generated_text": "生成されたテキスト"}の形式
        assistant_response = response_body.get('generated_text', '')
        
        # 応答の検証
        if not assistant_response:
            raise Exception("No response content from the model")
        
        # アシスタントの応答を会話履歴に追加
        messages.append({
            "role": "assistant",
            "content": assistant_response
        })
        
        # 成功レスポンスの返却
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST"
            },
            "body": json.dumps({
                "success": True,
                "response": assistant_response,
                "conversationHistory": messages
            })
        }
    except HTTPError as error:
        print(f"HTTP Error: {error.code} - {error.reason}")
        error_body = error.read().decode('utf-8')  # エラーレスポンスの本文を読む
        print(f"Error Response Body:\n{error_body}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST"
            },
            "body": json.dumps({
                "success": False,
                "error": f"API Error: {error.code} - {error.reason}",
                "details": error_body  # 詳細エラーも返す
            })
        }       
    except URLError as error:
        print(f"URL Error: {str(error)}")
        # タイムアウトエラーをより明確に処理
        error_message = str(error)
        if "timed out" in error_message:
            print("Request timed out - consider increasing Lambda timeout or checking API endpoint performance")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST"
            },
            "body": json.dumps({
                "success": False,
                "error": f"Connection Error: {error_message}",
                "suggestion": "API endpoint may be unresponsive or too slow to respond within timeout limits."
            })
        }
    except Exception as error:
        print("Error:", str(error))
        
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST"
            },
            "body": json.dumps({
                "success": False,
                "error": str(error)
            })
        }
