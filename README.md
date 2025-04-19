import pandas as pd

# Liste halinde 100 hayvan türü
animals = [
    "aslan","kaplan","fil","zürafa","zebra","gergedan","su aygırı","boz ayı",
    "kutup ayısı","panda","tilki","kurt","geyik","bizon","sincap","kirpi",
    "tavşan","hamster","kunduz","deniz aslanı","fok","balina","yunus",
    "köpek balığı","ahtapot","deniz atı","deniz yıldızı","yengeç","istiridye",
    "deniz kaplumbağası","penguen","kartal","şahin","baykuş","tavuk","ördek","kaz",
    "kuğu","pelikan","flamingo","martı","güvercin","sülün","bıldırcın","kelebek",
    "arı","uğur böceği","çekirge","karınca","yusufçuk","örümcek","yılan","timsah",
    "kertenkele","iguana","bukalemun","kurbağa","semender","inek","at","eşek","katır",
    "koyun","kuzu","keçi","domuz","tavus kuşu","deve","devekuşu","lama","kedi","köpek",
    "papağan","muhabbet kuşu","kaplumbağa","porsuk","antilop","manda","su samuru",
    "gelincik","sansar","çita","leopar","jaguar","panter","kanguru","koala","lemur",
    "surikat","tarantula","vatoz","palyaço balığı","tropikal balık","mürekkep balığı",
    "mersin balığı","beluga","mors","gila canavarı","su yılanı","köstebek"
]

# Her hayvan için iki farklı boyama kitabı stili prompt'u oluşturuluyor
prompts = []
for animal in animals:
    prompts.append(
        f"Line art stiliyle detaylı bir {animal} illüstrasyonu, doğal yaşam alanında, boyama için net ve geniş boş hatlarla."
    )
    prompts.append(
        f"Sevimli bir {animal} yavrusunu gösteren detaylı line art çizim, boş alanlar boyama için bırakılmış."
    )

# DataFrame'e dönüştürme
df = pd.DataFrame({
    "Sayfa": range(1, len(prompts) + 1),
    "Prompt": prompts
})

# Tabloyu kullanıcıya göster
import ace_tools as tools; tools.display_dataframe_to_user(name="200 Sayfalık Hayvan Boyama Kitabı Prompts", dataframe=df)
