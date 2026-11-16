#!/usr/bin/env python3
"""Original CMYK vector drop and one-page OpenInk print chart. Build-time only."""
from pathlib import Path
import math
import shutil
import subprocess
from reportlab.pdfgen import canvas
from reportlab.lib.colors import PCMYKColor as CMYKColor,HexColor,white
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'commun/inkora/assets'
OUTPUT=ROOT/'output/pdf/OpenInk-Page-de-test.pdf'
TMP=ROOT/'tmp/pdfs/openink'
OUTLINE=[('M',128,10),('C',109,45,24,144,16,209),('C',-2,284,61,316,128,316),
         ('C',195,316,258,284,240,209),('C',232,144,147,45,128,10),('Z',)]
LAYERS=[
 ('#00B7E8',CMYKColor(100,0,0,0),[('M',0,0),('L',256,0),('L',256,340),('L',0,340),('Z',)]),
 ('#ED008C',CMYKColor(0,100,0,0),[('M',-10,245),('C',43,267,108,153,174,132),('C',211,120,244,128,266,150),('L',270,340),('L',-10,340),('Z',)]),
 ('#F7EA00',CMYKColor(0,0,100,0),[('M',-10,305),('C',46,323,105,224,170,205),('C',215,192,241,204,270,222),('L',270,340),('L',-10,340),('Z',)]),
 ('#17191D',CMYKColor(0,0,0,100),[('M',40,335),('C',95,317,151,247,201,245),('C',230,243,250,257,270,282),('L',270,340),('L',40,340),('Z',)])]


def svg_path(commands):
    return ' '.join(str(part)for command in commands for part in command)


def pdf_path(c,commands):
    path=c.beginPath()
    for command in commands:
        op,*args=command
        if op=='M':path.moveTo(*args)
        elif op=='L':path.lineTo(*args)
        elif op=='C':path.curveTo(*args)
        elif op=='Z':path.close()
    return path


def draw_logo(c,x,y,height):
    c.saveState();c.translate(x,y+height);c.scale(height/320,-height/320)
    c.clipPath(pdf_path(c,OUTLINE),stroke=0,fill=0)
    c.setLineJoin(1);c.setLineWidth(8)
    for index,(_,color,commands)in enumerate(LAYERS):
        c.setFillColor(color);c.setStrokeColor(white)
        c.drawPath(pdf_path(c,commands),fill=1,stroke=int(index>0))
    c.restoreState()


def main():
    ASSETS.mkdir(parents=True,exist_ok=True);TMP.mkdir(parents=True,exist_ok=True);OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    paths=''.join(f'<path fill="{color}" d="{svg_path(commands)}"'+(' stroke="white" stroke-width="8" stroke-linejoin="round"'if i else'')+'/>'for i,(color,_,commands)in enumerate(LAYERS))
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 320"><defs><clipPath id="drop"><path d="{svg_path(OUTLINE)}"/></clipPath></defs><g clip-path="url(#drop)">{paths}</g></svg>\n'
    (ASSETS/'openink-logo.svg').write_text(svg)
    (ROOT/'linux/openink.svg').write_text(svg)
    c=canvas.Canvas(str(TMP/'logo.pdf'),pagesize=(256,320));draw_logo(c,0,0,320);c.save()
    subprocess.run(['pdftocairo','-png','-singlefile','-scale-to','1024','-transp',str(TMP/'logo.pdf'),str(TMP/'logo')],check=True)
    logo=Image.open(TMP/'logo.png').convert('RGBA')
    for size in (64,128,256,512,1024):
        icon=Image.new('RGBA',(size,size),(0,0,0,0));mark=logo.copy();mark.thumbnail((round(size*.8),round(size*.94)),Image.Resampling.LANCZOS)
        icon.alpha_composite(mark,((size-mark.width)//2,(size-mark.height)//2));icon.save(ASSETS/f'openink-{size}.png')
    for name,file in [('OpenInk','Lato-Regular.ttf'),('OpenInkBold','Lato-Bold.ttf')]:
        pdfmetrics.registerFont(TTFont(name,'/usr/share/fonts/truetype/lato/'+file))
    c=canvas.Canvas(str(OUTPUT),pagesize=A4);width,height=A4
    c.setTitle('OpenInk - Page de test CMJN');c.setAuthor('OpenInk')
    draw_logo(c,42,747,59)
    c.setFillColor(HexColor('#20283D'));c.setFont('OpenInkBold',33);c.drawString(103,773,'OpenInk')
    c.setFont('OpenInk',12);c.setFillColor(HexColor('#66748A'));c.drawString(105,752,'Page de test couleur - Epson XP-2200')
    c.setStrokeColor(HexColor('#DBE3ED'));c.line(44,727,width-44,727)
    c.setFont('OpenInkBold',16);c.setFillColor(HexColor('#20283D'));c.drawString(44,699,'Quatre couleurs, onze intensités')
    c.setFont('OpenInk',9);c.setFillColor(HexColor('#66748A'));c.drawString(44,681,'Compare les aplats, les dégradés et la finesse des traits. Une seule page A4.')
    for row,(letter,name,channel)in enumerate([('C','Cyan',0),('M','Magenta',1),('J','Jaune',2),('N','Noir',3)]):
        y=625-row*76
        components=[0,0,0,0];components[channel]=100
        c.setFillColor(CMYKColor(*components));c.circle(66,y,17,stroke=0,fill=1)
        c.setFont('OpenInkBold',18);c.setFillColor(HexColor('#20283D')if channel==2 else white);c.drawCentredString(66,y-6,letter)
        c.setFont('OpenInkBold',9);c.setFillColor(HexColor('#20283D'));c.drawCentredString(66,y-31,name)
        for col in range(11):
            value=100-col*10;x=115+32*col
            components=[0,0,0,0];components[channel]=value
            c.setFillColor(CMYKColor(*components));c.setStrokeColor(HexColor('#DCE3EC'));c.setLineWidth(.4)
            path=c.beginPath()
            for point in range(6):
                angle=math.pi/3*point
                px=x+17*math.cos(angle);py=y+17*math.sin(angle)
                if point:path.lineTo(px,py)
                else:path.moveTo(px,py)
            path.close();c.drawPath(path,fill=1,stroke=1)
            c.setFillColor(white if channel!=2 and value>=60 else HexColor('#20283D'));c.setFont('OpenInkBold',7)
            c.drawCentredString(x,y-2.5,str(value))
        c.setFillColor(HexColor('#66748A'));c.setFont('OpenInk',7);c.drawString(469,y+23,'Traits fins')
        c.setStrokeColor(CMYKColor(*([0]*channel+[100]+[0]*(3-channel))))
        for index,line_width in enumerate((.25,.5,1,2)):
            c.setLineWidth(line_width);c.line(469,y+10-8*index,548,y+10-8*index)
    c.setFillColor(HexColor('#20283D'));c.setFont('OpenInkBold',14);c.drawString(44,315,'Contraste et précision')
    for col in range(11):
        c.setFillColor(CMYKColor(0,0,0,col*10));c.rect(44+46*col,274,46,22,stroke=0,fill=1)
    c.setFillColor(CMYKColor(0,0,0,100))
    for index,size in enumerate((6,8,10,12)):
        c.setFont('OpenInk',size);c.drawString(44,244-index*22,f'OpenInk - Cyan, magenta, jaune et noir - texte {size} pt')
    c.setStrokeColor(CMYKColor(0,0,0,100));c.setLineWidth(.35)
    for i in range(13):
        c.line(430+i*8,155,430+i*8,247);c.line(430,155+i*7,526,155+i*7)
    c.setStrokeColor(HexColor('#DBE3ED'));c.line(44,124,width-44,124)
    c.setFont('OpenInk',9);c.setFillColor(HexColor('#66748A'))
    c.drawString(44,103,'Si une couleur manque : vérifier sa cartouche et les buses.')
    c.drawString(44,86,'Contrôle visuel CMJN ; ne remplace pas le test des buses Epson.')
    c.setFont('OpenInkBold',9);c.drawString(44,48,'OpenInk');c.setFont('OpenInk',8);c.drawRightString(width-44,48,'Test couleur - A4 - 1 page')
    c.showPage();c.save()
    shutil.copy2(OUTPUT,ASSETS/'test-page.pdf')
    print(OUTPUT)


if __name__=='__main__':main()
