"""Presentation-only colours. Firmware, readings and printed PDFs are unaffected."""
THEMES={'light':'Clair','dark':'Sombre'}

# Existing drawing code uses the light palette as its canonical colours.
# Foreground white stays white on coloured buttons and in the navigation bar.
DARK={
    '#F4F6FB':'#313338','#FFFFFF':'#2B2D31','#20283D':'#F2F3F5',
    '#818A9E':'#B5BAC1','#E8ECF3':'#45474E','#171F31':'#1E1F22',
    '#222D43':'#2B2D31','#293248':'#404249','#F7F8FC':'#232428',
    '#7560E8':'#5865F2','#6852DC':'#4752C4','#EBE8FB':'#3D3F48',
    '#E8EAF1':'#383A40','#F0F2F7':'#383A40','#F0EEFE':'#383746',
    '#F0F7FA':'#2B383D','#EDE9FF':'#383546','#ECEFFC':'#363843',
    '#EDEBF8':'#34343E','#ECEAF5':'#45474E','#EDF0F5':'#383A40',
    '#E5F8FC':'#163B49','#FDEDF4':'#48233D','#FFF7DF':'#453B20',
    '#354057':'#AEB3BD','#BD4D4D':'#FF9F9F','#B87A17':'#F0BE64',
    '#FBECEC':'#40262F','#FFF4DF':'#3B3322','#EDC8C8':'#83505E',
    '#ECD9B4':'#78643F','#FFF0EE':'#40252D','#F2C2BA':'#8B4B51',
    '#A52D26':'#FFA8A0','#8D4039':'#F5B6AE','#A16E19':'#F0BE64',
    '#66748A':'#B5BAC1','#6651CB':'#C3B5FF','#6753B4':'#C3B5FF',
    '#68658A':'#BAC4DF','#7260BB':'#C3B5FF','#7D719D':'#BDB5D6',
    '#8175A9':'#BDB5D6','#8273BA':'#BDB5D6','#C06C51':'#F4AE8F',
    '#C3C9D8':'#949BA4','#C4CADA':'#949BA4','#D5D9E6':'#5C5F66',
    '#D7DCE8':'#5C5F66','#DCE1EB':'#5C5F66','#4C856F':'#77D6B2',
    '#E8F1FF':'#22364B','#2563EB':'#83B6FF','#CBD2E1':'#5C5F66',
    '#8C98B0':'#949BA4','#8390AA':'#949BA4','#9BA8C0':'#B5BAC1',
    '#9FAAC0':'#B5BAC1','#B0BAD0':'#B5BAC1','#97A0B6':'#949BA4',
    '#A1A9B9':'#949BA4',
}


def color(value,theme='light',foreground=False):
    if not isinstance(value,str)or theme!='dark':return value
    key={'white':'#FFFFFF','black':'#20283D'}.get(value.lower(),value.upper())
    if foreground and key=='#FFFFFF':return '#FFFFFF'
    if foreground and key=='#7560E8':return '#B0B7FF'
    return DARK.get(key,value)


def widget_colors(master,options):
    root=master._root()if master is not None else None
    theme=getattr(root,'_openink_theme','light')
    foreground={'fg','foreground','activeforeground','disabledforeground','insertbackground'}
    backgrounds={'bg','background','activebackground','disabledbackground','highlightbackground',
                 'highlightcolor','selectbackground','selectforeground'}
    return {key:color(value,theme,key in foreground or key=='selectforeground')
            if key in foreground|backgrounds else value for key,value in options.items()}
