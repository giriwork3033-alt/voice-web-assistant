from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

out='/mnt/data/voice-web-assistant/report/one_page_report.pdf'
doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=36,leftMargin=36,topMargin=30,bottomMargin=30)
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='Title2', parent=styles['Title'], fontSize=20, leading=24, spaceAfter=8))
styles.add(ParagraphStyle(name='Head', parent=styles['Heading2'], fontSize=12, leading=14, textColor=colors.HexColor('#1f3a5f'), spaceBefore=6, spaceAfter=4))
styles.add(ParagraphStyle(name='Small', parent=styles['BodyText'], fontSize=8.8, leading=11))
styles.add(ParagraphStyle(name='Tiny', parent=styles['BodyText'], fontSize=8, leading=10))

story=[]
story.append(Paragraph('Voice Web Assistant - One Page Report', styles['Title2']))
story.append(Paragraph('Goal: accept voice input, fetch live internet data when needed, apply guardrails, and speak the result back through a polished browser interface.', styles['Small']))

story.append(Paragraph('1. Human-like avatar interface', styles['Head']))
story.append(Paragraph('The implemented app includes a lightweight animated AI avatar that reacts while the assistant is processing. For a production photorealistic version, the same response pipeline would connect ElevenLabs or another low-latency TTS stream into a real-time avatar provider such as Tavus, HeyGen Streaming Avatar, D-ID, or NVIDIA ACE. The flow is: user microphone -> STT -> LLM/tool response -> streaming TTS -> avatar lip-sync/video stream -> browser. This keeps the hard video synthesis outside the core app, reduces build risk, and still creates a realistic human-like interface. A production avatar would also support barge-in, emotion tags, mouth-viseme sync, and WebRTC delivery for low delay.', styles['Small']))

story.append(Paragraph('2. Tools and models used', styles['Head']))
data=[['Layer','Choice','Why'],['Frontend','React + Vite','Fast, clean UI with MediaRecorder audio capture.'],['Backend','FastAPI','Async Python API, easy file upload and tool orchestration.'],['STT','OpenAI Whisper API','Reliable speech-to-text with minimal setup.'],['LLM Agent','Gemini 2.5 Flash','Fast responses, tool calling, strong cost/performance.'],['Live Data','OpenWeather + Tavily','Weather and general internet lookup through explicit tools.'],['TTS','ElevenLabs','Natural spoken responses with simple API integration.'],['Guardrails','Input + output safety checks','Refuse unsafe requests before and after generation.']]
t=Table(data,colWidths=[1.0*inch,1.8*inch,4.0*inch])
t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#20344f')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),7.2),('LEADING',(0,0),(-1,-1),8.6),('GRID',(0,0),(-1,-1),0.25,colors.HexColor('#b7c0cc')),('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,1),(-1,-1),colors.HexColor('#f7f9fc'))]))
story.append(t)

story.append(Paragraph('3. Reducing lag and latency', styles['Head']))
story.append(Paragraph('The MVP already uses a simple async backend. To reduce latency further, the production version would stream each stage instead of waiting for full completion: streaming STT while the user speaks, Gemini token streaming, and streaming TTS so audio starts as soon as the first sentence is ready. Weather/search calls should run asynchronously, API clients should reuse HTTP connections, and common facts like weather can be cached for a short TTL. For avatar video, WebRTC is preferred over generating and downloading full videos. Additional optimizations include warm containers, smaller fast models for routing, parallel tool execution, request timeouts, and fallback responses when a tool fails.', styles['Small']))

story.append(Paragraph('Architecture', styles['Head']))
story.append(Paragraph('Mic -> React MediaRecorder -> FastAPI -> Whisper STT -> Input guardrail -> Gemini tool-calling -> Weather/Search tool -> Output guardrail -> ElevenLabs TTS -> Browser audio/avatar.', styles['Small']))

story.append(Paragraph('Safety and fit-and-finish', styles['Head']))
story.append(Paragraph('The app refuses clearly unsafe or offensive requests, avoids inventing live facts, shows transcript and answer cards, supports typed fallback testing, and continues to return text even when TTS keys are missing. This keeps the demo robust instead of brittle - because demos love breaking five minutes before submission.', styles['Small']))

doc.build(story)
print(out)
