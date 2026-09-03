import enum

class Mood(str, enum.Enum):
    FELIZ = "FELIZ"
    BEM = "BEM"
    CANSADO = "CANSADO"
    TRISTE = "TRISTE"
    IRRITADO = "IRRITADO"