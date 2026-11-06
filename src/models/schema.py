from dataclasses import dataclass,field
from datetime import datetime
from typing import Optional, Any

@dataclass
class RawItem:
    """raw input from the collection layer, field vary depending on the source"""
    source_id: str                      #identifier from the source
    external_id: str                     #the unique id of the item within the source
    url: str
    title: str
    content: str = ""
    snippet: str = ""
    published_at: Optional[datetime]=None
    raw_meta: dict[str,Any]=field(default_factory=dict) #additional raw metadata from the source

@dataclass
class Item:
    """normalize unified model"""
    source_id:str
    external_id:str
    url: str
    title: str
    content: str = ""
    snippet: str = ""
    published_at: Optional[datetime] = None
    fetched_at: Optional[datetime] = None
    category: str = "ai"
    lang: str = "en"
    raw_meta: dict[str, Any] = field(default_factory=dict)
    low_confidence_time: bool = False