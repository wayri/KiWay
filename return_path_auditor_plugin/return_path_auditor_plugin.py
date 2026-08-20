from __future__ import annotations

import csv
import os
import webbrowser
from pathlib import Path

import pcbnew
import wx

from .analysis import CopperSegment, ReferenceRegion, ReturnPathAnalyzer, ViaPoint
from .guided_ui import add_workflow, mark_primary, section


def mm(value): return float(pcbnew.ToMM(value))
def make_sortable(table):
    state={"column":0,"reverse":False}
    def sort(event):
        column=event.GetColumn();state["reverse"]=not state["reverse"] if column==state["column"] else False;state["column"]=column
        rows=[[table.GetItemText(row,col) for col in range(table.GetColumnCount())] for row in range(table.GetItemCount())];rows.sort(key=lambda row:row[column].casefold(),reverse=state["reverse"]);table.DeleteAllItems()
        for row in rows:i=table.InsertItem(table.GetItemCount(),row[0]);[table.SetItem(i,col,value) for col,value in enumerate(row[1:],1)]
    table.Bind(wx.EVT_LIST_COL_CLICK,sort)


class BoardPreview(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent, style=wx.BORDER_SIMPLE); self.result = None
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT); self.SetMinSize((-1, 260)); self.Bind(wx.EVT_PAINT, self.paint)
    def paint(self, _event):
        dc=wx.AutoBufferedPaintDC(self); dc.SetBackground(wx.Brush("#f7f9fb")); dc.Clear(); w,h=self.GetClientSize()
        if not self.result or not self.result.segments:
            dc.SetTextForeground("#566573"); dc.DrawLabel("Analyze the board to preview routed geometry and findings.",wx.Rect(10,10,w-20,h-20),wx.ALIGN_CENTER); return
        points=[point for segment in self.result.segments for point in (segment.start,segment.end)]
        xs=[p[0] for p in points]; ys=[p[1] for p in points]; margin=28
        scale=min((w-2*margin)/max(max(xs)-min(xs),1),(h-2*margin)/max(max(ys)-min(ys),1))
        project=lambda p:(margin+int((p[0]-min(xs))*scale),h-margin-int((p[1]-min(ys))*scale))
        colors={}; palette=("#1976d2","#2e7d32","#8e24aa","#ef6c00")
        for segment in self.result.segments:
            colors.setdefault(segment.layer,palette[len(colors)%len(palette)]); dc.SetPen(wx.Pen(colors[segment.layer],max(2,int(segment.width_mm*scale)))); dc.DrawLine(*project(segment.start),*project(segment.end))
        dc.SetBrush(wx.Brush("#f9a825")); dc.SetPen(wx.Pen("#7f6000"))
        for via in self.result.vias: dc.DrawCircle(*project(via.position),4)
        dc.SetBrush(wx.Brush("#c62828")); dc.SetPen(wx.Pen("#7f0000"))
        for finding in self.result.findings: dc.DrawCircle(*project((finding.x_mm,finding.y_mm)),6)


class ReturnPathAuditorPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name="KiWay Return-Path Auditor"; self.category="Analysis"; self.description="Find return-path discontinuities, unreferenced transitions, and routed stubs."; self.show_toolbar_button=True; self.icon_file_name=os.path.join(os.path.dirname(__file__),"icon.png"); self.dark_icon_file_name=self.icon_file_name; self.version="0.1.0"
    def Run(self):
        board=pcbnew.GetBoard()
        if board is None: wx.MessageBox("Open a PCB first.",self.name,wx.OK|wx.ICON_ERROR); return
        ReturnPathFrame(None,board).Show()


class ReturnPathFrame(wx.Frame):
    def __init__(self,parent,board):
        super().__init__(parent,title="KiWay Return-Path and Discontinuity Auditor",size=(1250,820)); self.board=board; self.result=None; self._build(); self.Centre()
    def _build(self):
        p=wx.Panel(self); root=wx.BoxSizer(wx.VERTICAL)
        self.guide=add_workflow(p,root,"Return-Path and Discontinuity Auditor","Audit signal transitions, reference continuity, routed branches, and differential geometry without modifying the PCB.",("Configure","Analyze","Review","Export"),lambda e:webbrowser.open((Path(__file__).with_name("help.html")).as_uri()))
        settings_box=section(p,"Audit Settings")
        settings_parent=settings_box.GetStaticBox()
        settings=wx.FlexGridSizer(3,6,7,8); settings.AddGrowableCol(1,1); settings.AddGrowableCol(3,1)
        self.ground=wx.TextCtrl(settings_parent,value="GND,AGND,DGND,PGND,VSS"); self.radius=wx.TextCtrl(settings_parent,value="2.0"); self.stub=wx.TextCtrl(settings_parent,value="5.0"); self.diff_gap=wx.TextCtrl(settings_parent,value="1.0"); self.diff_skew=wx.TextCtrl(settings_parent,value="0.5")
        for label,control in (("Return-net patterns",self.ground),("Return-via radius (mm)",self.radius),("Stub warning length (mm)",self.stub),("Diff uncoupling gap (mm)",self.diff_gap),("Diff skew limit (mm)",self.diff_skew)): settings.Add(wx.StaticText(settings_parent,label=label),0,wx.ALIGN_CENTER_VERTICAL);settings.Add(control,1,wx.EXPAND)
        analyze=mark_primary(wx.Button(settings_parent,label="Analyze Board"),"Analyze the current PCB without changing it"); analyze.Bind(wx.EVT_BUTTON,self.analyze); settings.Add(analyze,0,wx.EXPAND); export=wx.Button(settings_parent,label="Export CSV…");export.SetToolTip("Export the reviewed findings as CSV");export.Bind(wx.EVT_BUTTON,self.export);settings.Add(export,0,wx.EXPAND);settings_box.Add(settings,1,wx.EXPAND|wx.ALL,10);root.Add(settings_box,0,wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP,10)
        split=wx.SplitterWindow(p); left=wx.Panel(split); right=wx.Panel(split); ls=wx.BoxSizer(wx.VERTICAL); rs=wx.BoxSizer(wx.VERTICAL)
        self.table=wx.ListCtrl(left,style=wx.LC_REPORT); columns=(("Severity",85),("Check",190),("Net",150),("Layer",100),("Location",120),("Detail",430),("Suggested action",450))
        for i,(name,width) in enumerate(columns):self.table.InsertColumn(i,name,width=width)
        make_sortable(self.table)
        self.table.Bind(wx.EVT_LIST_ITEM_ACTIVATED,self.select); ls.Add(self.table,1,wx.EXPAND);left.SetSizer(ls)
        self.preview=BoardPreview(right);rs.Add(self.preview,1,wx.EXPAND);self.summary=wx.StaticText(right,label="No analysis yet.");rs.Add(self.summary,0,wx.EXPAND|wx.ALL,8);right.SetSizer(rs);split.SplitVertically(left,right,730);root.Add(split,1,wx.EXPAND|wx.ALL,8);p.SetSizer(root)
    def collect(self):
        segments=[]; vias=[]
        for item in self.board.GetTracks():
            name=str(getattr(item,"GetNetname",lambda:"")()); layer=str(getattr(item,"GetLayerName",lambda:"")())
            cls=str(getattr(item,"GetClass",lambda:"")()).upper()
            if "VIA" in cls:
                pos=item.GetPosition(); vias.append(ViaPoint(name,(mm(pos.x),mm(pos.y)),(layer,))); continue
            if hasattr(item,"GetStart") and hasattr(item,"GetEnd"):
                a,b=item.GetStart(),item.GetEnd();layer=str(self.board.GetLayerName(item.GetLayer()));segments.append(CopperSegment(name,layer,(mm(a.x),mm(a.y)),(mm(b.x),mm(b.y)),mm(item.GetWidth())))
        regions=[]
        for zone in getattr(self.board,"Zones",lambda:[])():
            box=zone.GetBoundingBox(); start,end=box.GetPosition(),box.GetEnd(); regions.append(ReferenceRegion(str(zone.GetNetname()),str(self.board.GetLayerName(zone.GetLayer())),(mm(start.x),mm(start.y),mm(end.x),mm(end.y))))
        return segments,vias,regions
    def analyze(self,_event):
        try:
            analyzer=ReturnPathAnalyzer(self.ground.GetValue().split(","));segments,vias,regions=self.collect();self.result=analyzer.audit(segments,vias,regions,float(self.radius.GetValue()),float(self.stub.GetValue()),float(self.diff_gap.GetValue()),float(self.diff_skew.GetValue()));self.table.DeleteAllItems()
            for finding in self.result.findings:
                row=(finding.severity,finding.check,finding.net,finding.layer,f"{finding.x_mm:.2f}, {finding.y_mm:.2f}",finding.detail,finding.remedy);index=self.table.InsertItem(self.table.GetItemCount(),row[0]);[self.table.SetItem(index,col,value) for col,value in enumerate(row[1:],1)]
            self.preview.result=self.result;self.preview.Refresh();self.summary.SetLabel(f"{len(segments)} routed segments | {len(vias)} vias | {len(regions)} reference regions | {len(self.result.findings)} findings")
            self.guide.set_step(2,"Review findings; double-click a row to cross-select its net.")
        except Exception as exc:wx.MessageBox(str(exc),"Audit failed",wx.OK|wx.ICON_ERROR)
    def select(self,event):
        net=self.table.GetItemText(event.GetIndex(),2)
        try:
            for item in self.board.GetTracks():
                if str(getattr(item,"GetNetname",lambda:"")())==net:getattr(item,"SetSelected",lambda:None)()
            pcbnew.Refresh()
        except Exception:pass
    def export(self,_event):
        if not self.result:return
        with wx.FileDialog(self,"Export findings",wildcard="CSV (*.csv)|*.csv",style=wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT) as dialog:
            if dialog.ShowModal()!=wx.ID_OK:return
            with open(dialog.GetPath(),"w",newline="",encoding="utf-8") as handle:
                writer=csv.writer(handle);writer.writerow(["severity","check","net","layer","x_mm","y_mm","detail","remedy"]);writer.writerows((f.severity,f.check,f.net,f.layer,f.x_mm,f.y_mm,f.detail,f.remedy) for f in self.result.findings)
            self.guide.set_step(3,"Use the exported evidence in design review or resolve findings in PCB Editor.")
