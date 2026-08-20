from __future__ import annotations
import csv,os,webbrowser
from pathlib import Path
import pcbnew,wx
from .analysis import PadNode,analyze_decoupling,infer_regulators
from .guided_ui import add_workflow, mark_primary, section

def make_sortable(table):
    state={"column":0,"reverse":False}
    def sort(event):
        column=event.GetColumn();state["reverse"]=not state["reverse"] if column==state["column"] else False;state["column"]=column;rows=[[table.GetItemText(r,c) for c in range(table.GetColumnCount())] for r in range(table.GetItemCount())];rows.sort(key=lambda row:row[column].casefold(),reverse=state["reverse"]);table.DeleteAllItems()
        for row in rows:i=table.InsertItem(table.GetItemCount(),row[0]);[table.SetItem(i,c,v) for c,v in enumerate(row[1:],1)]
    table.Bind(wx.EVT_LIST_COL_CLICK,sort)

class PdnDecouplingPlugin(pcbnew.ActionPlugin):
    def defaults(self):self.name="KiWay PDN and Decoupling Planner";self.category="Analysis";self.description="Audit power-rail topology and local decoupling placement.";self.show_toolbar_button=True;self.icon_file_name=os.path.join(os.path.dirname(__file__),"icon.png");self.dark_icon_file_name=self.icon_file_name;self.version="0.1.0"
    def Run(self):
        board=pcbnew.GetBoard()
        if board is None:return
        PdnFrame(None,board).Show()
class PdnFrame(wx.Frame):
    def __init__(self,parent,board):super().__init__(parent,title="KiWay PDN and Decoupling Planner",size=(1150,760));self.board=board;self.findings=[];self._build();self.Centre()
    def _build(self):
        p=wx.Panel(self);r=wx.BoxSizer(wx.VERTICAL)
        self.guide=add_workflow(p,r,"PDN and Decoupling Planner","Qualify rail-to-ground capacitors, check load proximity, and review regulator candidates without changing placement.",("Classify","Analyze","Review","Export"),lambda e:webbrowser.open(Path(__file__).with_name("help.html").as_uri()))
        settings_box=section(p,"Rail Classification and Placement Limits")
        settings_parent=settings_box.GetStaticBox()
        g=wx.FlexGridSizer(2,6,7,8);g.AddGrowableCol(1,1);g.AddGrowableCol(3,1);self.rails=wx.TextCtrl(settings_parent,value="VCC*,VDD*,VBAT*,*VOUT*,+*V,3V*,5V*,12V*");self.ground=wx.TextCtrl(settings_parent,value="GND*,AGND*,DGND*,PGND*,VSS*");self.distance=wx.TextCtrl(settings_parent,value="3.0");self.loads=wx.TextCtrl(settings_parent,value="U*")
        for label,c in (("Rail patterns",self.rails),("Ground patterns",self.ground),("Maximum capacitor distance (mm)",self.distance),("Load references",self.loads)):g.Add(wx.StaticText(settings_parent,label=label));g.Add(c,1,wx.EXPAND)
        a=mark_primary(wx.Button(settings_parent,label="Analyze PDN"),"Analyze power pins and nearby valid decoupling capacitors");a.Bind(wx.EVT_BUTTON,self.analyze);g.Add(a);self.summary=wx.StaticText(settings_parent,label="No analysis yet.");g.Add(self.summary,1,wx.ALIGN_CENTER_VERTICAL);settings_box.Add(g,1,wx.EXPAND|wx.ALL,8);r.Add(settings_box,0,wx.EXPAND|wx.ALL,10)
        self.table=wx.ListCtrl(p,style=wx.LC_REPORT);[(self.table.InsertColumn(i,name,width=width)) for i,(name,width) in enumerate((("Severity",90),("Rail",160),("Load pin",140),("Check",190),("Evidence",500)))];self.table.Bind(wx.EVT_LIST_ITEM_ACTIVATED,self.select);r.Add(self.table,1,wx.EXPAND|wx.ALL,8);ex=wx.Button(p,label="Export CSV");ex.Bind(wx.EVT_BUTTON,self.export);r.Add(ex,0,wx.ALIGN_RIGHT|wx.ALL,8);p.SetSizer(r)
        make_sortable(self.table)
    def pads(self):
        rows=[]
        for fp in self.board.GetFootprints():
            ref,value=str(fp.GetReference()),str(fp.GetValue())
            for pad in fp.Pads():pos=pad.GetPosition();rows.append(PadNode(ref,str(pad.GetNumber()),str(pad.GetNetname()),float(pcbnew.ToMM(pos.x)),float(pcbnew.ToMM(pos.y)),value))
        return rows
    def analyze(self,_event):
        pads=self.pads();self.findings=analyze_decoupling(pads,self.rails.GetValue(),self.ground.GetValue(),load_patterns=self.loads.GetValue(),maximum_distance_mm=float(self.distance.GetValue()));regs=infer_regulators(pads);self.table.DeleteAllItems()
        for f in self.findings:row=(f.severity,f.rail,f.load,f.check,f.detail);i=self.table.InsertItem(self.table.GetItemCount(),row[0]);[self.table.SetItem(i,c,v) for c,v in enumerate(row[1:],1)]
        self.summary.SetLabel(f"{len(set(p.net for p in pads if p.net))} nets | {len(regs)} regulator candidates | {len(self.findings)} load-pin checks");self.guide.set_step(2,"Review findings; double-click a load pin to cross-select its component.")
    def select(self,event):
        target=self.table.GetItemText(event.GetIndex(),2).split(".",1)[0]
        try:
            for fp in self.board.GetFootprints():
                if str(fp.GetReference())==target:fp.SetSelected()
            pcbnew.Refresh()
        except Exception:pass
    def export(self,_event):
        if not self.findings:return
        with wx.FileDialog(self,"Export PDN audit",wildcard="CSV (*.csv)|*.csv",style=wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT) as d:
            if d.ShowModal()!=wx.ID_OK:return
            with open(d.GetPath(),"w",newline="",encoding="utf-8") as h:w=csv.writer(h);w.writerow(["severity","rail","load","check","detail"]);w.writerows((f.severity,f.rail,f.load,f.check,f.detail) for f in self.findings)
