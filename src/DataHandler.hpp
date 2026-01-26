#ifndef DATA_HANDLER_HPP
#define DATA_HANDLER_HPP

#include "Bar.hpp"
#include <vector>

class DataHandler {
    private:
        std::vector<Bar> data;
        int index;
    public:
        DataHandler();
        bool hasNext() const;
        Bar getNext();
};


#endif